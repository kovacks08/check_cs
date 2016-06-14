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
        required=True
    )

    parser.add_argument(
        '-t', '--template',
        dest='template_name',
        type=str,
        choices=template_names,
        default='Centos64',
        help='The template name.'
             ' You must select a template that runs linux with ssh enabled.'
             ' It must also have the password reset enabled.',
        required=True
    )

    parser.add_argument(
        '-d', '--domain',
        dest='domain_name',
        type=str,
        help='Domain name',
        required=True
    )

    parser.add_argument(
        '-a', '--account',
        dest='account_name',
        default='',
        type=str,
        help='Account name',
    )

    parser.add_argument(
        '-o', '--test_type',
        dest='test_type',
        type=str,
        default='basic',
        help='Type of test: basic,network,storage,templates,snapshot_policy,lifecycle',
        required=True
    )

    parser.add_argument(
        '-k', '--keep_snapshots',
        dest='keep_snapshots',
        action='store_true',
        help='Keep volume with snapshot policies to test afterwards if storage_test is storage',
    )

    parser.add_argument(
        '-i', '--iso_url',
        dest='iso_url',
        type=str,
        default='http://10.220.2.77/CentOS-6.5-x86_64-minimal.iso',
        help='ISO URL for upload test',
    )

    parser.add_argument(
        '-u', '--template_url',
        dest='template_url',
        type=str,
        default='http://10.220.2.77/centos64.ova',
        help='Template URL for upload test',
    )

    # Assign parsed arguments
    args = parser.parse_args()
    zone_name = args.zone_name
    template_name = args.template_name
    domain_name = args.domain_name
    account_name = args.account_name
    test_type = args.test_type
    iso_url = args.iso_url
    template_url = args.template_url
    keep_snapshots = args.keep_snapshots

    #print('keep_snapshots: %s' % keep_snapshots)
    #sys.exit()

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
    if account_name == '':
        account_name = domain_name

    ### Check the account name exists 
    request = {
        'domain': domain_id,
        'listall': 'True',
        'name': account_name,
    }
    result=admin_api.listAccounts(request)
    print('Account name %s\n' % account_name)
    #pprint(result)
    if result == {} or 'account' not in result:
        output(
            message=('No account found matching the account name %s for the specified domain name %s\n' % (account_name, domain_name)),
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
    if user_context is False:
        output('Some error obtaining keys from user %s' % user_name, success=False)

    if 'api_key' not in user_context:
        output('Some error obtaining keys from user %s' % user_name, success=False)

    #pprint(user_context)

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
            break
    if template_id is None:
        output(
            'The template is not available in the selected zone.\n'
            'The following templates are available:\n',
            success=False
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
        output( 'Username %s not found in existing domain %s\n' %
            (user_name,domain_id), 
            success = False
        )
        sys.exit()

    user_id=user_result['user'][0]['id']
    account_result = api.listAccounts(request)
    if account_result == {} or account_result['count'] == 0:
        output( 'Username %s not found in existing domain %s\n' %
            (user_name,domain_id),
            success = False
        )
    account_id=account_result['account'][0]['id']

    print('Using template %s with ID: %s' % (template_name, template_id))

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

    print(
        'Using service offering %s with ID %s\n' %
        (service_offering_name, service_offering_id),
    )

    ### We wil create a network specifically for each test_type test ###
    process_name='val-%s-%s-%d' % (test_type,user_name,time.time())
    network_name='%s-net' % (process_name)
    account_name=user_name

    processes = []
    # Select the function depending on the test type
    if test_type == 'basic':
        process = multiprocessing.Process(target=basic_test, args=(zone_id, network_name, template_id, domain_id, account_name, api,),)
        output_name='out_%s' % process_name
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
    elif test_type == 'network':
        output_name='out_%s' % process_name
        process = multiprocessing.Process(target=network_test, args=(zone_id, network_name, template_id, domain_id, account_name, ostype_id, output_name,api,),)
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
    elif test_type == 'storage':
        output_name='out_%s' % process_name
        process = multiprocessing.Process(target=storage_test, args=(zone_id, network_name, template_id, domain_id, account_name, ostype_id, keep_snapshots, api,),)
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
    elif test_type == 'template':
        output_name='out_%s' % network_name
        process = multiprocessing.Process(target=template_test, args=(zone_id, network_name, template_id, domain_id, account_name, ostype_id, iso_url, template_url, api,),)
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
    elif test_type == 'snapshot_policy':
        output_name='out_%s-%d' % (account_name,time.time())
        process = multiprocessing.Process(target=validate_snapshot_policy, args=(zone_id, domain_id, account_name, output_name, api,),)
        output_name=output_name.replace('-net','')
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
    elif test_type == 'lifecycle':
        ### For a lifecycle policy we create a process for every single vm the user that has lfv in the name ###
        request = {
            'domainid': domain_id,
            'zone_id': zone_id,
            'name': 'lfv'
        }
        result = api.listVirtualMachines(request)
        if result == {} or 'virtualmachine' not in result:
            print('Could not find any vm for the user matching lfv\n')
            sys.exit()
        virtualmachines = result['virtualmachine']
        network_name2 = 'validation-net'
        ip_address2 = '192.168.10.2'
        gateway2 = '192.168.10.1'
        volume_name = 'validation-volume'
        disk_offering_name = 'EBS'
        volume_size = '10'
        for virtualmachine in virtualmachines:
            vm_id = virtualmachine['id']
            process = multiprocessing.Process(target=lifecycle_test, args=(zone_id, vm_id, domain_id, account_name, api, network_name2, volume_name, disk_offering_name, volume_size, ip_address2, gateway2,),)
            output_name='out_{}'.format(vm_id)
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
    else:
        print('Wrong test type')
        sys.exit()

    # Perform the tests on the network we created ###

    #process.name = process_name
    #process.start()
    #processes.append(process)
    #if process.is_alive():
        #print(
            #'%s - %s is Started'
            #% (datetime.datetime.now(), process.name)
        #)
    #else:
        #print('ERROR: %s failed to Start' % process.name)

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
