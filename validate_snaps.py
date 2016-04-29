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
        '-u', '--user',
        dest='template_user',
        type=str,
        default='user',
        help='The template user name.',
    )

    # Assign parsed arguments
    args = parser.parse_args()
    zone_name = args.zone_name
    template_user = args.template_user

    #### Obtain a user context for user api call ###
    user_context=get_usercontext(template_user,admin_api)
    if 'api_key' not in user_context:
        print('Some error obtaining keys from user %s' % user_name)
        sys.exit()
    pprint(user_context)

    ### We test how to create an api object for the user
    ### We create a user apicall ###
    ### We need to get the user id and the keys ###
    mytempfile='~/.vdcapi.snaptestuser' 
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

    ### We use the user name as the domain id ###
    user_name=template_user

    request = {
        'name': user_name,
        'listall': 'True',
    }
    result=api.listDomains(request)
    if result == {} or 'domain' not in result:
        output(
            message='No domain found matching the user name %s' % template_user,
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

    # Perform the tests on the network we created ###
    processes = []

    account_name=user_name
    process = multiprocessing.Process(target=validate_snashot_policy, args=(
        zone_id,
        domain_id,
        account_name,
        api,
        ),
    )
    process.name = 'snapshot_test@%s' % template_user
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
                        '\n%s - %s is Finished, check the out_%s file'
                        % (datetime.datetime.now(),
                           process.name,
                           process.name.split("@")[1],
                           )
                    )
                    finished_processes.append(process.name)
        time.sleep(2)
