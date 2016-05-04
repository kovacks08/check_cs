#!/usr/bin/env python

import vdc_api_call
import argparse
import os
import sys
import colorama
import time
from pprint import pprint


class Parser:

    def __init__(self):
        self.parser = argparse.ArgumentParser()
        self.parser.add_argument(
            '-z',
            '--zone_name',
            dest='zone_name',
            type=str,
            required=True,
            help='CloudStack Zone Name',
            )
        self.parser.add_argument(
            '-c',
            '--config_file',
            dest='config_file',
            type=str,
            required=False,
            default='~/.vdcapi',
            help='vdcapi config file',
            )

        self.args = self.parser.parse_args()
        self.zone_name= self.args.zone_name
        self.config_file= self.args.config_file

def output(message, success=True):
    if success:
        print(colorama.Fore.WHITE + message)
    elif success=='relative':
        print(colorama.Fore.WHITE + message)
    else:
        sys.stderr.write(colorama.Fore.YELLOW)
        sys.stderr.write('FAILURE OCCURRED\n')
        sys.stderr.write('Error was: %s\n' % message)
        sys.stderr.write(colorama.Fore.RESET)
        sys.exit(1)

def wait_for_job(job_id, api):
    while(True):
        request = {
            'jobid': job_id,
        }
        result= api.queryAsyncJobResult(request)
        if 'jobresult' in result:
            return result['jobresult']
        time.sleep(2)

if __name__ == '__main__':
    parser = Parser()

    zone_name = parser.zone_name
    config_file = parser.config_file

    home = os.path.expanduser('~')

    # Create api caller
    ### api = vdc_api_call.create_api_caller(config_file)

    print('/'.join([home,config_file]))
    api = vdc_api_call.create_api_caller('/'.join([home,config_file]))

    ### Getting the zoneid ###

    request = {
        'name': zone_name
        }

    result = api.listZones(request) 
    pprint(result)

    if result == {} or 'zone' not in result:
        output(
            'Zone %s not found.' % zone_name,
            success=False
        )
    else:
        zone_id=result['zone'][0]['id'] 
        zone_name=result['zone'][0]['name'] 
        output(
            'Zone %s found. ID: %s' % (zone_name, zone_id)
        )

    ## Checking for the PrivateWithGatewayServices Network offering ##
    networkoffering_name='PrivateWithGatewayServices'

    request = {
    'name': networkoffering_name
    }

    networkoffering_result=api.listNetworkOfferings(request)
    if  networkoffering_result == {} or networkoffering_result['count'] == 0:
        output( 'No network offering PrivateWithGatewayServices found', success='relative' )

        ### Placeholder # In case offerintg does not exists create it ###
        ### Let's create the network offering

        request= {
            'conservemode': 'True',
            'displaytext': 'PrivateWithGatewayServices',
            'egressdefaultpolicy': 'False',
            'forvpc': 'False',
            'guestiptype': 'Isolated',
            'isdefault': 'True',
            'ispersistent': 'False',
            'supportedServices': "Vpn,Dhcp,Dns,Firewall,Lb,UserData,SourceNat,StaticNat,PortForwarding",
            "serviceProviderList[0].service": 'Vpn',
            "serviceProviderList[0].provider": 'VirtualRouter',
            "serviceProviderList[1].service": 'Dhcp',
            "serviceProviderList[1].provider": 'VirtualRouter',
            "serviceProviderList[2].service": 'Dns',
            "serviceProviderList[2].provider": 'VirtualRouter',
            "serviceProviderList[3].service": 'Firewall',
            "serviceProviderList[3].provider": 'VirtualRouter',
            "serviceProviderList[4].service": 'Lb',
            "serviceProviderList[4].provider": 'VirtualRouter',
            "serviceProviderList[5].service": 'UserData',
            "serviceProviderList[5].provider": 'VirtualRouter',
            "serviceProviderList[6].service": 'SourceNat',
            "serviceProviderList[6].provider": 'VirtualRouter',
            "serviceProviderList[7].service": 'StaticNat',
            "serviceProviderList[7].provider": 'VirtualRouter',
            "serviceProviderList[8].service": 'PortForwarding',
            "serviceProviderList[8].provider": 'VirtualRouter',
            'name': 'PrivateWithGatewayServices',
            'specifyipranges': 'False',
            'specifyvlan': 'False',
            'state': 'Enabled',
            'traffictype': 'Guest',
        }

        pprint(request)
        result=api.createNetworkOffering(request)
        pprint(result)
        if result == {} or 'networkoffering' not in result:
            output(
                 'Could not create network offering'
                 ,success='relative'
            )
        else:
            networkoffering=result['networkoffering']
            output(
                 message='network offering created with id %s' % networkoffering['id'],
            )
            request={
                'id': networkoffering['id'],
                'state': 'enabled' 
            }
            result=api.updateNetworkOffering(request)
            networkoffering=result['networkoffering']
            output(
                message='network offering state: %s' % networkoffering['state'],
            )

    else:
        networkoffering_id=networkoffering_result['networkoffering'][0]['id']
        networkoffering_state=networkoffering_result['networkoffering'][0]['state']
        output( 'Networkofferingid %s found. ID: %s. State %s' % (networkoffering_name,networkoffering_id,networkoffering_state))


    ## Checking for Compute Offerings ###

    ## Requests for service offerings ##

    compute_requests={}
    compute_requests['Tiny Instance']={
        'displaytext': 'Tiny Instance',
        'name': 'Tiny Instance',
        'cpunumber': '1',
        'cpuspeed': '50',
        'memory': '256',
        'tags': 'vms',
    }
    compute_requests['Small Instance']={
        'displaytext': 'Small Instance',
        'name': 'Small Instance',
        'cpunumber': '1',
        'cpuspeed': '500',
        'memory': '512',
        'tags': 'vms',
    }
    compute_requests['Huge Instance']={
        'displaytext': 'Huge Instance',
        'name': 'Huge Instance',
        'cpunumber': '8',
        'cpuspeed': '1000',
        'memory': '16384',
        'tags': 'vms',
    }

    request = {}
    result = api.listServiceOfferings(request)
    if result == {} or 'serviceoffering' not in result:
        output(
            message='Could not find service offerings',
            success='relative'
        )
    service_offerings=result['serviceoffering']

    service_offerings_names={'Tiny Instance', 'Small Instance', 'Huge Instance'}

    for name in service_offerings_names:
        output(
            message='Looking for service offering %s\n' % name,
        )
        service_offering_id='Null'
        for service_offering in service_offerings:
            if service_offering['name'] == name:
                 service_offering_id=service_offering['id']
                 service_offering_name=service_offering['name']
                 break
        if service_offering_id == 'Null':
            output(
                message='Could not find service offering %s \n' % name,
                success='relative'
            )
            request=compute_requests[name]
            result=api.createServiceOffering(request)
            if result == {} or 'serviceoffering' not in result:
                output(
                    message='Could not create service offering %s \n %s'
                    % (name,result),
                    success='relative'
                )
            else:
                service_offering=result['serviceoffering']
                output(
                    message='Service offering %s created with id %s \n' % (name,service_offering['id']),
                )
            
        else:
            output(
                message='Compute offering %s found. ID: %s' %
                (service_offering_name, service_offering_id),
            )

    ### Look for disk  service offering EBS ###
    # Obtain EBS disk offering ID

    disk_offering_name='EBS'

    request = {}
    result = api.listDiskOfferings(request)
       
    disk_offering_id='Null'

    for disk in result['diskoffering']:
        if disk['name'] == disk_offering_name:
            disk_offering_id = disk['id']

    # Check if disk offering exists
    if disk_offering_id == 'Null':
        output(
            'Disk offering %s not found' % disk_offering_name,
            success='relative'
        )

        request={
            'displaytext':  disk_offering_name,
            'name':  disk_offering_name,
            'customized': 'True',
            'displayoffering': 'True',
            'tags': 'ebs',
        }
        result=api.createDiskOffering(request)
        if result == {} or 'diskoffering' not in result:
            output(
                message='Could not create Disk offering %s \n %s'
                % (disk_offering_name,result),
                success='relative'
            )
        else:
            disk_offering=result['diskoffering']
            output(
                message='Disk offering %s created with. ID %s' % (disk_offering_name,disk['id']),
            )
    else:
        output(
            'Disk offering %s found. ID: %s' % (disk_offering_name,disk_offering_id)
        )

    #### Placeholder ### Create service offerings if missing ###

    
    ### Check if base domain exists ###
    parentdomain_name='VDCC'
    
    request = {
        'name': parentdomain_name
    }

    parentdomain_result = api.listDomains(request)
    if parentdomain_result == {} or 'domain' not in parentdomain_result:
        output(
            'Parent domain %s not found \n'
            '%s' 
            % (parentdomain_name,parentdomain_result),
            success='relative'
        )

        ### Create Parent domain ###
        request = {
           'name': parentdomain_name,
        }
        domain_result = api.createDomain(request)
        if domain_result == {}:
            output(
                 "Could not crate domain  %s" % parentdomain_name ,
                 success='relative'
            )
            output(parentdomain_result)
        else:
            parentdomain_id = domain_result['domain']['id']
            output(
                'Parent domain %s created. ID: %s' % (parentdomain_name,parentdomain_id)
            )
    else:
        parentdomain_id = parentdomain_result['domain'][0]['id']
        output(
            'Parent domain %s found. ID: %s' % (parentdomain_name,parentdomain_id)
        )


    ### List available Templates
    template_names={'Debian74','Centos64'}


    ### Get the Os types ###
    

    request={
    }

    result=api.listOsTypes(request)
    ostype_list=result['ostype'] 
    ### pprint(ostype_list)
    ostype_ids={}
    for ostype in ostype_list:
        if ostype['description']=='Debian GNU/Linux 7(64-bit)':
            ostype_ids['Debian']=ostype['id']
        elif ostype['description']=='CentOS 6.4 (64-bit)': 
            ostype_ids['CentOS']=ostype['id']

    template_requests={}
    template_requests['Debian74']={
        'displaytext': 'Debian74',
        'format': 'OVA',
        'hypervisor': 'VMWare',
        'name': 'Debian74',
        'ostypeid': ostype_ids['Debian'],
        'url': 'http://10.220.2.77/debian74.ova',
        'zoneid': zone_id,
        'isfeatured': 'True',
        'ispublic': 'True',
        'passwordenabled': True,
        'isdynamicallyscalable': True,
    }
    template_requests['Centos64']={
        'displaytext': 'Centos64',
        'format': 'OVA',
        'hypervisor': 'VMWare',
        'name': 'Centos64',
        'ostypeid': ostype_ids['CentOS'], 
        'url': 'http://10.220.2.77/centos64.ova',
        'zoneid': zone_id,
        'isfeatured': 'True',
        'ispublic': 'True',
        'passwordenabled': True,
        'isdynamicallyscalable': True,
    }

    request = {
        'templatefilter': 'executable',
        'zoneid': zone_id,
    }

    result = api.listTemplates(request)
    if result == {} or 'template' not in result:
        output(
            'No valid templates found'
        )
    else:
        templates = result['template']
        ### pprint(templates)
        for template_name in template_names:
              template_id = 'Null'
              for template in templates:
                        if template['name'] == template_name:
                            template_id=template['id']
                            template_ready=template['isready']
                            if not template_ready:
                                output(
                                    'template %s not ready:'  % (template_name,),
                                    success='relative'
                                )
                                pprint(template)
                            break
              if template_id == 'Null':
                    output(
                        message='Could not find template %s \n' % template_name,
                        success='relative'
                    )
                    ### We attempt to deploy the template
                    request=template_requests[template_name]
                    result = api.registerTemplate(request)

                    if 'template' in result:
                        template_id=result['template'][0]['id'] 
                        output(
                            'Registering template %s with id %s ...' 
                            % (template_name,template_id),
                            success='relative'
                        )
                        
                    else:
                        output(
                            'ERROR: Failed to register template%s. '
                            ' Response was %s\n' %
                            (template_name, result),
                            success='relative'
                        )


              else:
                    output(
                        message='Template %s found. ID: %s. Is ready: %s' % (template_name,template_id,template_ready)
                    )

    print(colorama.Fore.WHITE + '\n' )
