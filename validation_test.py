#!/usr/bin/env python
from __future__ import print_function
import colorama
import vdc_api_call as vdc
import sys
import time
import multiprocessing
import datetime
import socket
import argparse
import logging
import random
from pprint import pprint
from vdc_api_call.config import Config
from functions import *

# Check Python version
if sys.version_info[0] == 2 and sys.version_info[1] < 7:
    print("\n######################################################")
    print("Pyhton's versions previous then 2.7 are not supported.")
    print("######################################################\n")
    exit()

import paramiko

if __name__ == '__main__':
    # Create the api access object
    admin_api = vdc.create_api_caller()

    # Prepare to do pretty colours on output
    colorama.init()

    # ### Determine the zone ### #

    # List available ZOnes
    request = {}
    zone_result = admin_api.listZones(request)

    zone_names = [zone['name']
                  for zone
                  in zone_result['zone']]

    # List available Templates
    request = {
        'templatefilter': 'executable',
    }

    temp_result = admin_api.listTemplates(request)

    template_names = [template['name']
                      for template
                      in temp_result['template']
                      if template['isready']]

    # Parse the arguments
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-z', '--zone',
        dest='zone_name',
        type=str,
        choices=zone_names,
        default=zone_names[0],
        help='The zone name.',
    )

    parser.add_argument(
        '-t', '--template',
        dest='template_name',
        type=str,
        choices=template_names,
        default='Centos64',
        help='The template name.'
             ' You must select a template that runs linux with ssh enabled.'
             ' It must also have the password reset enabled.'
    )

    parser.add_argument(
        '-d', '--domain',
        dest='domain_name',
        type=str,
        help='Domain name',
    )

    parser.add_argument(
        '-a', '--account',
        dest='user_name',
        type=str,
        help='Account name',
    )

    parser.add_argument(
        '-o', '--test_type',
        dest='test_type',
        type=str,
        default='user',
        help='Type of test: basic,network,storage,templates,snapshot_policy',
    )

    # Assign parsed arguments
    args = parser.parse_args()
    zone_name = args.zone_name
    template_name = args.template_name
    domain_name = args.domain_name
    account_name = args.account_name
    test_type = args.test_type


    ### Obtain the domain id ###

    request = {
        'name': domain_name,
        'listall': 'True',
    }
    result=admin_api.listDomains(request)
    if result == {} or 'domain' not in result:
        output(
            message='No domain found matching the domain name %s' % domain_name,
            success=False,
        )

    domains=result['domain']
    domain_id=domains[0]['id']

    ### Verify Account Name ###

    ### If account name is not specified use domain name as account name ###
    if account_name == {}:
        account_name = domain_name

    ### Check the account name exists 
    request = {
        'domain': domain_id,
        'listall': 'True',
        'name': account_name,
    }
    result=admin_api.listAccounts(request)
    if result == {} or 'account' not in result:
        output(
            message='No account found matching the account name %s for the specified domain name %s\n' % (account_name, domain_name)
            success=False,
        )

    accounts=result['account']
    account_id=accounts[0]['id']

    ### Validate the user name (the same as the account_name) ###
    user_name = account_name

    request = {
            'domainid': domain_id,
            'account': account_name,
            'listall': 'True',
            'username': user_name,
        }

    user_result = admin_api.listUsers(request)
    if user_result == {} or user_result['count'] == 0 :
        print( 'Username %s not found in existing domain %s\n' %
            (user_name,domain_id)
            )
        sys.exit()

    user_id=user_result['user'][0]['id']

    

    #### Obtain a user context for user api call ###
    user_context=get_usercontext(user_name,admin_api)
    if 'api_key' not in user_context:
        print('Some error obtaining keys from user %s' % user_name)
        sys.exit()
    pprint(user_context)

    ### We test how to create an api object for the user
    ### We create a user apicall ###
    ### We need to get the user id and the keys ###
    mytempfile='~/.vdcapi.basictestuser' 
    config = Config(mytempfile)
    config.update_context( 'default', api_url=user_context['api_url'] )
    config.update_context( 'default', api_key=user_context['api_key'] )
    config.update_context( 'default', api_secret=user_context['api_secret'] )
    api = vdc.caller(config)
    ###################################################

    # Obtain zone ID
    for zone in zone_result['zone']:
        if zone['name'] == zone_name:
            zone_id = zone['id']
            break

    # Check if template is present in selected zone and for current user
    request = {
        'templatefilter': 'executable',
        'zoneid': zone_id,
    }
    temp_result = api.listTemplates(request)

    template_id = None

    # Obtain template ID
    for template in temp_result['template']:
        if template['name'] == template_name:
            template_id = template['id']
            ostype_id = template['ostypeid']
            output('template_id %s\n' % template_id)
            break
    if template_id is None:
        sys.stderr.write(
            'The template is not available in the selected zone.\n'
            'The following templates are available:\n'
        )
        for template in temp_result['template']:
            print('Found the following templates')
            print(template['name'])
        sys.exit()

    ### We use the user name as the domain id ###

    request = {
        'name': user_name,
        'listall': 'True',
    }
    result=api.listDomains(request)
    if result == {} or 'domain' not in result:
        output(
            message='No domain found matching the user name %s' % user_name,
            success=False,
        )

    domain=result['domain']
    domain_id=domain[0]['id']

    request = {
            'domainid': domain_id,
            'listall': True,
            'username': user_name
        }
    
    user_result = api.listUsers(request)
    if user_result == {} or user_result['count'] == 0 :
        print( 'Username %s not found in existing domain %s\n' %
            (user_name,domain_id)
            )
        sys.exit()

    user_id=user_result['user'][0]['id']
    account_result = api.listAccounts(request)
    if account_result == {} or account_result['count'] == 0:
        print( 'Username %s not found in existing domain %s\n' %
            (user_name,domain_id)
        )
        sys.exit()
    account_id=account_result['account'][0]['id']

    output(
        message='Using template %s with ID: %s' % (template_name, template_id)
    )

    request = {
        'listall': 'True',  
        'name': 'Medium Instance',
        }
    result = api.listServiceOfferings(request)
    if result == {} or 'serviceoffering' not in result:
        output(
            message='Could not find service offering.',
            success=False,
        )
    service_offering_id = result['serviceoffering'][0]['id']
    service_offering_name = result['serviceoffering'][0]['displaytext']

    output(
        message='Using service offering %s with ID %s\n' %
        (service_offering_name, service_offering_id),
    )

    ### We wil create a network specifically for each test_type test ###
    process_name='validation-%s-%s-%d' % (test_type,user_name,time.time())
    network_name='%s-net' % (process_name)
    account_name=user_name

    # Select the function depending on the test type
    if test_type == 'basic':
        process = multiprocessing.Process(target=basic_test, args=(zone_id, network_name, template_id, domain_id, account_name, api,),)
        output_name='out_%s' % network_name
    elif test_type == 'network':
        process = multiprocessing.Process(target=network_test, args=(zone_id, network_name, template_id, domain_id, account_name, ostype_id, api,),)
        output_name='out_%s' % network_name
    elif test_type == 'storage':
        process = multiprocessing.Process(target=storage_test, args=(zone_id, network_name, template_id, domain_id, account_name, ostype_id, api,),)
        output_name='out_%s' % network_name
    elif test_type == 'template':
        process = multiprocessing.Process(target=template_test, args=(zone_id, network_name, template_id, domain_id, account_name, ostype_id, api,),)
        output_name='out_%s' % network_name
    elif test_type == 'snapshot_policy':
        process = multiprocessing.Process(target=validate_snapshot_policy, args=(zone_id, domain_id, account_name, api,),)
        output_name='out_%s' % account_name
    else: 
        print('Wrong test type')
        sys.exit()
    

    # Perform the tests on the network we created ###
    processes = []

    process.name = process_name
    process.start()
    processes.append(process)
    if process.is_alive():
        print(
            '%s - %s is Started'
            % (datetime.datetime.now(), process.name)
        )
    else:
        print('ERROR: %s failed to Start' % process.name)

    finished_processes = []
    while len(finished_processes) < len(processes):
        # Print dots while running
        print('.', end='')
        sys.stdout.flush()
        # Check if process is still running
        for process in processes:
            if process.name not in finished_processes:
                if process.is_alive():
                    # Process is still running
                    pass
                else:
                    process.join()
                    print(
                        '\n%s - %s is Finished, check the %s file'
                        % (datetime.datetime.now(),
                           process.name,
                           output_name 
                           )
                    )
                    finished_processes.append(process.name)
        time.sleep(2)
