#! /usr/bin/env python
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
from functions import *

# Check Python version
if sys.version_info[0] == 2 and sys.version_info[1] < 7:
    print("\n######################################################")
    print("Pyhton's versions previous then 2.7 are not supported.")
    print("######################################################\n")
    exit()

###import paramiko


def output(message, success=True):
    if success:
        print(message)
    else:
        sys.stderr.write(colorama.Fore.YELLOW)
        sys.stderr.write('FAILURE OCCURRED\n')
        sys.stderr.write('Error was: %s\n' % message)
        sys.stderr.write(colorama.Fore.RESET)
        sys.exit(1)

if __name__ == '__main__':

    # Prepare to do pretty colours on output
    colorama.init()

    # Parse the arguments

    # Create the api access object
    api = vdc.create_api_caller()
    # ### Determine the zone ### #
    # List available ZOnes
    request = {}
    zone_result = api.listZones(request)
    zone_names = [zone['name']
                  for zone
                  in zone_result['zone']]
    # List available Templates
    request = {
        'templatefilter': 'executable',
    }
    temp_result = api.listTemplates(request)
    template_names = [template['name']
                      for template
                      in temp_result['template']
                      if template['isready']]
    # List available offerings
    request = {}
    offer_result = api.listServiceOfferings(request)
    offer_names = [serviceoffering['name']
                      for serviceoffering
                      in offer_result['serviceoffering']]

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-z', '--zone',
        dest='zone_name',
        type=str,
        choices=zone_names,
        default=zone_names[0],
        help='The zone name.',
    )

    ##parser.add_argument(
        ##'-t', '--template',
        ##dest='template_name',
        ##type=str,
        ##choices=template_names,
        ##default='Centos 6.4 (64-bit)',
        ##help='The template name.'
             ##' You must select a template that runs linux with ssh enabled.'
             ##' It must also have the password reset enabled.'
    ##)

    parser.add_argument(
        '-o', '--serviceoffering',
        dest='service_offering',
        type=str,
        choices=offer_names,
        default='Tiny Instance',
        help    ='Compute Service Offering'
                'Small Instance and Tiny Instance should exist by default',
    )

    parser.add_argument(
        '-b', '--base',
        dest='base_username',
        type=str,
        default='user',
        help='The base user name.',
    )

    parser.add_argument(
        '-p', '--parentdomain',
        dest='parent_domain',
        type=str,
        default='VDCC',
        help='The base for domain names',
    )

    parser.add_argument(
        '-d', '--domain',
        dest='domain_name',
        default='',
        type=str,
        help='Domain name for the accounts',
    )

    ##parser.add_argument(
        ##'-u', '--usernumber',
        ##dest='user_number',
        ##type=int,
        ##default=5,
        ##help='Number of users',
    ##)

    ##parser.add_argument(
        ##'-n', '--vmnumber',
        ##dest='vm_number',
        ##type=int,
        ##default=5,
        ##help='Number of vms per network',
    ##)


    args = parser.parse_args()
    # Assign parsed arguments
    zone_name = args.zone_name
    ##template_name = args.template_name
    base_username = args.base_username
    parent_domain = args.parent_domain
    domain_name = args.domain_name
    ##user_number = args.user_number
    ##vm_number = args.vm_number
    compute_service_offering = args.service_offering


    # Obtain zone ID
    for zone in zone_result['zone']:
        if zone['name'] == zone_name:
            zone_id = zone['id']
            break

    ## List all the templates with the name lfv ##

    # Check if template is present in selected zone
    request = {
        'templatefilter': 'executable',
        'zoneid': zone_id,
    }

    temp_result = api.listTemplates(request)
    template_ids = {}

    # Obtain template ID
    for template in temp_result['template']:
        if 'lfv' in template['name']:
            template_name=template['name']
            template_id=template['id']
            template_ids[template_name]=template_id
    if template_ids is None:
        sys.stderr.write(
            'Did not find templates with name lfv\n'
        )

    pprint(template_ids)

    ### list to keep track of the domain_ids and user_ids

    domain_ids = {}
    account_ids = {}


    ### We evaluate if we create new domains or accounts on existing domain ###
    if domain_name=='':
        print ('Domain name not defined. Creating new domains per account ... \n') 
        ### We get the ID of the parent domain ###
        print("Parent domain name: %s\n" % parent_domain)

        request = {
            'name': parent_domain
        }

        parentdomain_result = api.listDomains(request)
        if parentdomain_result == {} or 'domain' not in parentdomain_result:
            print('ERROR: Parent domain %s not found.\n Result was %s\n' % (parent_domain,parentdomain_result))
            sys.exit()

        parentdomain_id = parentdomain_result['domain'][0]['id']
        print("Parent domain id: %s\n" % parentdomain_id)

        ### Creating domains and users ###
        ### Create the username
        account_name='lfv-%s-%s' % (base_username,zone_name)
        print( "Account name is %s" % account_name )
        domain_name=account_name
        DomainAccountIds=create_domainandaccount(account_name,parentdomain_id,api)
        account_id=DomainAccountIds['AccountId']
        domain_id=DomainAccountIds['DomainId']
        domain_ids[account_name]=domain_id
        account_ids[account_name]=account_id

    else:
        print ('Domain name $s defined. Creating accounts in this domain. Ignoring parent domain ...\n')
        request = {
            'name': domain_name,
            'listall': 'True'
        }
        result=api.listDomains(request)
        if result == {} or 'domain' not in result:
            print ('No domain found with name %s\n' % domain_name)
            sys.exit()
        else:
            domain=result['domain'][0]
            print ('Domain path is %s\n' % domain['path'])
            domain_id= domain['id']
            print ('Domain id is %s\n' % domain_id)

        ### Creating domains and users ###
        ### Create the username
        account_name='lfv-%s-%s' % (base_username,zone_name)
        print( "Account name is %s" % account_name )
        account_id=create_account(account_name,domain_id,api)
        domain_ids[account_name]=domain_id
        account_ids[account_name]=account_id


    ### Validate the Service Offering ###
    request = {}
    result = api.listServiceOfferings(request)

    if result == {} or 'serviceoffering' not in result:
        output( message='Could not find service offering.', success=False,)

    service_offerings=result['serviceoffering']
    service_offering_id='Null'

    for service_offering in service_offerings:
   	    if service_offering['name'] == compute_service_offering:
	        service_offering_id=service_offering['id']
	        service_offering_name=service_offering['name']
	        break

    if service_offering_id == 'Null':
	    output(
           message='Could not find service offering.',
          success=False,
        )

    output(
        message='Using service offering %s with ID %s\n' %
        (service_offering_name, service_offering_id),
	    )


    ### 

    network_ids = {}
    vm_ids={}

    processes = []

    for account_name in account_ids:
        account_id=account_ids[account_name]
        domain_id=domain_ids[account_name]
        print ( 'account name %s:' % account_name )
        network_name='net-'+account_name
        displaytext=network_name
        ### First we create the networks
        ###network_ids[account_name]=create_network(zone_id, domain_id, displaytext, network_name, account_id, api)
        network_ids[account_name]=create_network(zone_id, domain_id, account_name, network_name, api, sys.stdout, gateway='192.168.0.1')
        ### Then we create a parallel process for the vms
        output(
            message='created network with IDs: %s' %
            ','.join(network_ids),
            )
        for template_name in template_ids:
            vm_name='vm-%s-%s' % (account_name,template_name)
            template_id= template_ids[template_name]
            pprint(vm_name)
            process = multiprocessing.Process(target=deploy_vm, args=(
                vm_name,
                zone_id,
                network_ids[account_name],
                domain_id,
                account_name,
                sys.stdout,
                template_id,
                api,
                '',
                'Medium Instance',
                'True',
                )
            )         
            process.name = 'process@%s' % vm_name
            process.start()
            processes.append(process)
            if process.is_alive():
                print(
                    '%s - %s is Started'
                    % (datetime.datetime.now(), process.name)
                )
            else:
                print('ERROR: %s failed to Start' % process.name)
            
    ### Loop to check the status of the processess ###
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
                        '\n%s - %s is Finished'
                        % (datetime.datetime.now(),
                           process.name
                           )
                    )
                    finished_processes.append(process.name)
        time.sleep(30)
        
