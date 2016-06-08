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

def output(message, success=True, warning=False):
    if success:
        if warning:
            print(colorama.Fore.YELLOW + message)
            print(colorama.Fore.RESET)
        else:
            print(colorama.Fore.GREEN + message)
            print(colorama.Fore.RESET)
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

    ##networkoffering_names={'PrivateWithGatewayServices','IPAC/IPVPN','Unmanaged')}

    ###networkoffering_name='PrivateWithGatewayServices'

    request = {
    ## 'name': networkoffering_name
    }

    networkoffering_result=api.listNetworkOfferings(request)
    if  networkoffering_result == {} or networkoffering_result['count'] == 0:
        output( 'No network offerings found', warning=True )
    existing_networkofferings=networkoffering_result['networkoffering']
    existing_networkoffering_names=[]
    existing_networkoffering_ids={}
    for networkoffering in existing_networkofferings:
        networkoffering_name=networkoffering['name']
        existing_networkoffering_names.append(networkoffering_name)
        existing_networkoffering_ids[networkoffering_name]=networkoffering['id']

    networkoffering_requests={}
    networkoffering_requests['PrivateWithGatewayServices']={
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
        'networkrate': '3000',
    }

    networkoffering_requests['IPAC/IPVPN']={
        'conservemode': 'True',
        'displaytext': 'IPAC/IPVPN',
        'egressdefaultpolicy': 'True',
        'forvpc': 'False',
        'guestiptype': 'Shared',
        'isdefault': 'False',
        'ispersistent': 'False',
        'supportedServices': "Dhcp,Dns,UserData",
        "serviceProviderList[0].service": 'Dhcp',
        "serviceProviderList[0].provider": 'VirtualRouter',
        "serviceProviderList[1].service": 'Dns',
        "serviceProviderList[1].provider": 'VirtualRouter',
        "serviceProviderList[2].service": 'UserData',
        "serviceProviderList[2].provider": 'VirtualRouter',
        'name': 'IPAC/IPVPN',
        'specifyipranges': 'True',
        'specifyvlan': 'True',
        'state': 'Enabled',
        'traffictype': 'Guest',
        'networkrate': '3000',
    }


    for networkoffering_name in networkoffering_requests:
        ### If the network offering does not exist create it
        if networkoffering_name in existing_networkoffering_names:
            output( 'Networkoffering %s found. ID: %s.' % (networkoffering_name,existing_networkoffering_ids[networkoffering_name]) )
        else:
            request=networkoffering_requests[networkoffering_name]
            result=api.createNetworkOffering(request)
            if result == {} or 'networkoffering' not in result:
                output(
                    'Could not create network offering'
                    ,warning=True
                )
            else:
                networkoffering=result['networkoffering']
                networkoffering_name=networkoffering['name']
                existing_networkoffering_names.append(networkoffering_name)
                existing_networkoffering_ids[networkoffering_name]=networkoffering['id']
                output(
                    message='network offering%s  created with id %s' % (networkoffering_name,networkoffering['id']),
                )
                request={
                    'id': networkoffering['id'],
                    'state': 'enabled' 
                }
                result=api.updateNetworkOffering(request)
                output(
                    message='network offering state: %s' % networkoffering['state'],
                )


    networkoffering_id=existing_networkoffering_ids['PrivateWithGatewayServices']

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

    ### Create combination of CPU requests ###
    ram_options=['512', '1024', '2048', '4096', '6144', '8192', '12288', '16384', '24576', '32768', '65536', '131072']
    cpu_options=['1', '2', '3','4', '5', '6', '7', '8', '9', '10', '11', '12']
    cpuspeed='2000' ### CPU LIMIT ###

    for cpu in cpu_options:
        for ram in ram_options:
            compute_offering_displaytext='%s MB RAM,%sx2.0 GHz CPUs' % (ram,cpu)
            compute_offering_name='%s-%s' % (ram,cpu) 
            compute_requests[compute_offering_name]={
                'displaytext': compute_offering_displaytext,
                'name': compute_offering_name,
                'cpunumber': cpu,
                'cpuspeed': cpuspeed,
                'memory': ram,
                'tags': 'vms',
            }

    request = {}
    result = api.listServiceOfferings(request)
    if result == {} or 'serviceoffering' not in result:
        output(
            message='Could not find service offerings',
            warning=True
        )
    service_offerings=result['serviceoffering']

    #service_offerings_names={'Tiny Instance', 'Small Instance', 'Huge Instance'}

    for name in compute_requests:
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
                warning=True
            )
            request=compute_requests[name]
            result=api.createServiceOffering(request)
            if result == {} or 'serviceoffering' not in result:
                output(
                    message='Could not create service offering %s \n %s'
                    % (name,result),
                    warning=True
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

    ### Create disk offerings ###
    # Obtain EBS disk offering ID

    disk_requests={}
    disk_requests['EBS']={
        'displaytext': 'EBS',
        'name': 'EBS',
        'customized': 'True',
        'displayoffering': 'True',
        'tags': 'ebs',
    }
    disk_requests['mirrored']={
        'displaytext': 'mirrored',
        'name': 'mirrored',
        'customized': 'True',
        'displayoffering': 'True',
        'tags': 'mirrored',
    }
    disk_requests['protected']={
        'displaytext': 'mirrored',
        'name': 'mirrored',
        'customized': 'True',
        'displayoffering': 'True',
        'tags': 'protected',
    }

    root_disk_sizes = ['10','20','40','60','80','100']
    for size in root_disk_sizes:
        disk_offering_name='%sGB VM' % size
        disk_offering_displaytext='%sGB root disk' % size
        disk_requests[disk_offering_name]={
            'name': disk_offering_name,
            'displaytext': disk_offering_displaytext,
            'customized': 'False',
            'disksize': size,
            'displayoffering': 'True',
            'tags': 'vms',
        }

    for disk_offering_name in disk_requests:
        
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
                warning=True
            )
    
            request=disk_requests[disk_offering_name]
            result=api.createDiskOffering(request)
            if result == {} or 'diskoffering' not in result:
                output(
                    message='Could not create Disk offering %s \n %s'
                    % (disk_offering_name,result),
                    warning=True
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
            warning=True
        )

        ### Create Parent domain ###
        request = {
           'name': parentdomain_name,
        }
        domain_result = api.createDomain(request)
        if domain_result == {}:
            output(
                 "Could not crate domain  %s" % parentdomain_name ,
                 warning=True
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


    ### Get the Os types ###
    request={
    }

    result=api.listOsTypes(request)
    ostype_list=result['ostype'] 
    ### pprint(ostype_list)
    ostype_ids={}
    for ostype in ostype_list:
        if ostype['description']=='Debian GNU/Linux 7(64-bit)':
            ostype_ids['Debian74']=ostype['id']
        elif ostype['description']=='CentOS 6.4 (64-bit)': 
            ostype_ids['Centos64']=ostype['id']
        elif ostype['description']=='Windows Server 2012 R2 (64-bit)':
            ostype_ids['Windows2012R2']=ostype['id']

    template_requests={}
    ##nic_types={'E1000','Vmxnet3'}
    nic_types={'E1000','Vmxnet3'}
    ##disk_types={'scsi','ide','osdefault'}
    disk_types={'scsi','osdefault'}
    template_base_list={'Windows2012R2','Debian74','Centos64'}
    template_url={
        'Windows2012R2':'http://10.220.2.77/WIN2012R2SE-MH-160316.ova',
        'Debian74':'http://10.220.2.77/debian74.ova',
        'Centos64':'http://10.220.2.77/centos64.ova'
    }


    # Create the request for all the combinations of template base, nic type and storage type
    
    template_names=[]
    template_requests={}

    for template_base in template_base_list:
        ## We create a template with only the base name and vmxnet3 and osdefault
        template_name=template_base
        template_names.append(template_name)
        template_requests[template_name]={
            'name': template_name,
            'displaytext': template_name,
            'format': 'OVA',
            'hypervisor': 'VMWare',
            'ostypeid': ostype_ids[template_base],
            'url': template_url[template_base],
            'zoneid': zone_id,
            'isfeatured': 'False',
            'ispublic': 'True',
            'passwordenabled': 'True',
            'isdynamicallyscalable': 'True',
            'isdynamicallyscalable': 'True',
            'details[0].nicAdapter': 'Vmxnet3',
            'details[0].rootDiskController': 'osdefault',
            'details[0].dataDiskController': 'osdefault',
       }
       


        ### After that we go for the 
        for nic_type in nic_types:
            for disk_type in disk_types:
                template_name='%s-lfv-%s-%s' % (template_base,nic_type,disk_type)
                template_names.append(template_name)
                template_requests[template_name]={
                    'name': template_name,
                    'displaytext': template_name,
                    'format': 'OVA',
                    'hypervisor': 'VMWare',
                    'ostypeid': ostype_ids[template_base],
                    'url': template_url[template_base],
                    'zoneid': zone_id,
                    'isfeatured': 'False',
                    'ispublic': 'True',
                    'passwordenabled': True,
                    'isdynamicallyscalable': True,
                    'isdynamicallyscalable': True,
                    'details[0].nicAdapter': nic_type,
                    'details[0].rootDiskController': disk_type,
                    'details[0].dataDiskController': disk_type,
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
                                    warning=True
                                )
                                pprint(template)
                            break
              if template_id == 'Null':
                    output(
                        message='Could not find template %s \n' % template_name,
                        warning=True
                    )
                    ### We attempt to deploy the template
                    request=template_requests[template_name]
                    result = api.registerTemplate(request)

                    if 'template' in result:
                        template_id=result['template'][0]['id'] 
                        output(
                            'Registering template %s with id %s ...' 
                            % (template_name,template_id),
                            warning=True
                        )
                        
                    else:
                        output(
                            'ERROR: Failed to register template%s. '
                            ' Response was %s\n' %
                            (template_name, result),
                            warning=True
                        )


              else:
                    output(
                        message='Template %s found. ID: %s. Is ready: %s' % (template_name,template_id,template_ready)
                    )

    print(colorama.Fore.WHITE + '\n' )
