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

# Check Python version
if sys.version_info[0] == 2 and sys.version_info[1] < 7:
    print("\n######################################################")
    print("Pyhton's versions previous then 2.7 are not supported.")
    print("######################################################\n")
    exit()

import paramiko


def output(message, success=True):
    if success:
        print(message)
    else:
        sys.stderr.write(colorama.Fore.YELLOW)
        sys.stderr.write('FAILURE OCCURRED\n')
        sys.stderr.write('Error was: %s\n' % message)
        sys.stderr.write(colorama.Fore.RESET)
        sys.exit(1)


def wait_stop(vm_id, api, timeout=75):
    current_time = 0
    while current_time < timeout:
        request = {
            'id': vm_id,
        }
        result = api.listVirtualMachines(request)
        if result['virtualmachine'][0]['state'] == 'Stopped':
            return True
        current_time += 2
        time.sleep(2)
    return False

def wait_for_job(job_id, api):
    while(True):
        request = {
            'jobid': job_id,
        }
        result = api.queryAsyncJobResult(request)
        if 'jobresult' in result:
            return result['jobresult']
        time.sleep(2)

def ssh_command(command, hostname, password, port, timeout=75):
    username = 'root'
    port = int(port)
    session = paramiko.SSHClient()
    session.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    start_time = time.time()
    duration = 0
    while duration < timeout:
        try:
            session.connect(hostname, port, username, password, timeout=1)
            stdin, stdout, stderr = session.exec_command(command)
            stdin.close()
            return stdout.read()
        except socket.error as error:
            # allow retries on connection failure, e.g: after reboot

            # Handle different error message propagation
            if error.strerror is None:
                message = error.message
            else:
                message = error.strerror

            # Delay unless we timed out
            if 'timed out' not in message:
                time.sleep(1)
        except paramiko.AuthenticationException as error:
            # Allow time for password reset script
            time.sleep(1)
        duration = time.time() - start_time
    # Return None in case of timeout
    return ''

def create_volume_fromsnap(volume_name,snapshot_id,zone_id,api,net_out):
    ### Send message out ###
    net_out.write(
        'Create volume: %s' %
        (volume_name),
    )

    request = {
        'name': volume_name,
        'zoneid': zone_id,
        'volume_size': 15,
        'snapshotid': snapshot_id,
    }
    result = api.createVolume(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed job to create volume  %s. '
            ' Response was %s\n' %
            (volume_name, result),
        )
        ### We dont error control cleanup
        return False

    result = wait_for_job(result['jobid'], api)

    if result == {} or result['volume']['id'] == []:
        net_out.write(
            'ERROR: Failed to create volume %s.'
            ' Response was %s\n' % (volume_name, result),
        )
        ### We dont error control cleanup
        return False

    volume_id = result['volume']['id']
    net_out.write(
        'Volume %s successfully created with ID %s.\n'
        % (volume_name, volume_id)
    )

    net_out.write('Waiting for volume in ready state\n')
    current_time = 0
    timeout = 60
    while current_time < timeout:
        request = {
            'id': volume_id,
            'listall': 'True',
        }
        result = api.listVolumes(request)
        if result['volume'][0]['state'] == 'Ready':
            net_out.write('Volume in %s state\n' % result['volume'][0]['state'])
            return volume_id
        elif result['volume'][0]['state'] == 'Allocated':
            net_out.write('Volume in %s state\n' % result['volume'][0]['state'])
            return volume_id
        elif result['volume'][0]['state'] == 'Uploaded':
            net_out.write('Volume in %s state\n' % result['volume'][0]['state'])
            return volume_id
        current_time += 2
        time.sleep(2)
    return False

def upload_volume(volume_name,volume_url,disk_offering_name,zone_id,account_name,domain_id,api,net_out):

    ### Send message out ###
    net_out.write(
        'Upload volume: %s from url %s\n' %
        (volume_name,volume_url),
    )

    ### Get the disk offering id name
    # Obtain EBS disk offering ID
    request = {}
    result = api.listDiskOfferings(request)

    for disk in result['diskoffering']:
        if disk['name'] == disk_offering_name:
            disk_offering_id = disk['id']

    # Check if disk offering exists
    if disk_offering_id == '':
        net_out.write(
            'ERROR: Impossible create an volume. Disk offering %s not found' % disk_offering_name
        )
        return False

    request = {
        'name': volume_name,
        'zoneid': zone_id,
        'diskofferingid': disk_offering_id,
        'url': volume_url,
        'format': 'OVA',
        'account': account_name,
        'domainid': domain_id,
    }
    result = api.uploadVolume(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed job to upload volume %s. '
            ' Response was %s\n' %
            (volume_name, result),
        )
        ### We dont error control cleanup
        return False

    result = wait_for_job(result['jobid'], api)

    if result == {} or result['volume']['id'] == []:
        net_out.write(
            'ERROR: Failed to upload volume on zone %s.'
            ' Response was %s\n' % (zone_id, result),
        )
        ### We dont error control cleanup
        return False

    volume_id = result['volume']['id']
    net_out.write(
        'Volume successfully uploaded on zone %s with ID %s.\n'
        % (volume_id, zone_id)
    )

    net_out.write('Waiting for volume in ready state')
    current_time = 0
    timeout = 60
    while current_time < timeout:
        request = {
            'id': volume_id,
            'listall': 'True',
        }
        result = api.listVolumes(request)
        if result['volume'][0]['state'] == 'Ready':
            net_out.write('Volume in %s state' % result['volume'][0]['state'])
            return volume_id
        elif result['volume'][0]['state'] == 'Allocated':
            net_out.write('Volume in %s state' % result['volume'][0]['state'])
            return volume_id
        elif result['volume'][0]['state'] == 'Uploaded':
            net_out.write('Volume in %s state' % result['volume'][0]['state'])
            return volume_id
        current_time += 2
        time.sleep(2)
    return False
    


def create_volume(volume_name,volume_size,disk_offering_name,zone_id,account_name,domain_id,api,net_out):

    ### Send message out ### 
    net_out.write(
        'Create volume: %s' %
        (volume_name), 
    )

    ### Get the disk offering id name
    # Obtain EBS disk offering ID
    request = {}
    result = api.listDiskOfferings(request)

    for disk in result['diskoffering']:
        if disk['name'] == disk_offering_name:
            disk_offering_id = disk['id']

    # Check if disk offering exists
    if disk_offering_id == '':
        net_out.write(
            'ERROR: Impossible create an volume. Disk offering %s not found' % disk_offering_name
        )
        return False

    # Create volumes (ESB - size volume_size)
    ##volume_name = ('zone_test_%s' % network_id)

    request = {
        'name': volume_name,
        'zoneid': zone_id,
        'diskofferingid': disk_offering_id,
        'size': volume_size,
        'account': account_name,
        'domainid': domain_id,
    }
    result = api.createVolume(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed job to create volume %s. '
            ' Response was %s\n' %
            (volume_name, result),
        )
        ### We dont error control cleanup
        return False

    result = wait_for_job(result['jobid'], api)

    if result == {} or result['volume']['id'] == []:
        net_out.write(
            'ERROR: Failed to create volume on zone %s.'
            ' Response was %s\n' % (zone_id, result),
        )
        ### We dont error control cleanup
        return False

    volume_id = result['volume']['id']
    net_out.write(
        'Volume %s successfully created on zone %s.\n'
        % (volume_id, zone_id)
    )

    return(volume_id)

def migrate_volume(volume_id,api,net_out,migrate_back):

    ### Migrate volume to a different candidate object_storage

    ### Find the current storage pool id for the volume
    request = {
        'id': volume_id,
        'listall': 'True',
    }
    result = api.listVolumes(request)

    if result == {}:
        net_out.write(
            'ERROR: Failed to find volume on zone %s.'
            ' Response was %s\n' % (zone_id, result),
        )
        return False

    volume_name = result['volume'][0]['name']
    storage_pool_id = result['volume'][0]['storageid']
    storage_pool_name = result['volume'][0]['storage']
    net_out.write(
       'Volume %s with id %s is currently stored on storatge %s \n' 
       % (volume_name, volume_id,storage_pool_name),
    )

    ### Find a candidate pool to migrated the volume to
    request = {
        'id': volume_id,
    }
    result = api.findStoragePoolsForMigration(request)

    if result == {}:
        net_out.write(
            'ERROR: Failed to find candidate destination to migrate volume %s'
            'Response was %s\n' % (volume_name, result),
        )
        return False

    storage_pool_candidate_id='Null'
    storage_pools=result['storagepool']
    for pool in storage_pools:
        if pool['suitableformigration']==True:
            storage_pool_candidate_id=pool['id'] 
            storage_pool_candidate_name=pool['name'] 
            ##print ('storage_pool_candidate_id: %s\n' % storage_pool_candidate_id)
            ##print ('storage_pool_candidate_name: %s\n' % storage_pool_candidate_name)
            ##print ('-------------------------------------\n')
            ## We get the first valid result
            break

    if storage_pool_candidate_id=='Null':
        net_out.write(
            'ERROR: Failed to find candidate destination to migrate volume %s \n'
            ' Response was %s\n' % (volume_name, result),
        )
        return False
    else:
         net_out.write(
            'candidate storage id for migration is %s with id %s \n' % (storage_pool_candidate_id, storage_pool_candidate_name),
        )

    ### Actually attempt the migration operation
    request = {
        'volumeid': volume_id,
        'storageid': storage_pool_candidate_id,
        'livemigrate': 'True'
    }
    result = api.migrateVolume(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed job to migrate volume  %s'
            ' Response was %s\n' %
            (volume_name, result),
        )
        return False

    result = wait_for_job(result['jobid'], api)

    if result == {} or 'volume' not in result:
        net_out.write(
            'ERROR: Failed to migrate volume  %s.'
            ' Response was %s\n' % (volume_id, result),
        )
        return False
    
    result_volume=result['volume']

    storage_pool_destination_name = result_volume['storage']
    storage_pool_destination_id = result_volume['storageid']
    net_out.write(
        'Volume %s successfully migrated to storage %s\n'
        % (volume_name, storage_pool_destination_id)
    )

    ### In case migrate back option is used we migrate the volume back to the original location
    if migrate_back == 'True':
        storage_pool_candidate_id=storage_pool_id
        storage_pool_candidate_name=storage_pool_name

        request = {
            'volumeid': volume_id,
            'storageid': storage_pool_candidate_id,
            'livemigrate': 'True'
            }

        ###print ("request\n")
        ###print(request)
        result = api.migrateVolume(request)
        
        if result == {} or 'jobid' not in result.keys():
            net_out.write(
                'ERROR: Failed job to migrate back volume  %s'
                'Response was %s\n' %
                (volume_name, result),
            )
            return False
        
        result = wait_for_job(result['jobid'], api)

        if result == {} or 'volume' not in result:
            net_out.write(
                'ERROR: Failed to migrate back volume  %s.'
                ' Response was %s\n' % (volume_id, result),
            )
            return False

        result_volume=result['volume']
        storage_pool_destination_name = result_volume['storage']
        storage_pool_destination_id = result_volume['storageid']

        net_out.write(
            'Volume %s successfully migrated to storage %s\n'
            % (volume_name, storage_pool_destination_id)
        )

    return storage_pool_destination_id


def attach_volume(volume_id,vm_id,api,net_out):
    # Attach volumes
    net_out.write( 'Attaching volume %s to vm %s:\n'  %
                    (volume_id,vm_id))
    request = {
        'id': volume_id,
        'virtualmachineid': vm_id,
    }
    result = api.attachVolume(request)

    if result == {} or 'jobid' not in result.keys():
        ### We dont error control cleanup
        net_out.write(
            'ERROR: Failed to create job to attach volume on VM %s. '
            ' Response was %s\n' % (vm_id, result),)
        ### Adding clean up stuff
        return False

    result = wait_for_job(result['jobid'], api)
    if result == {} or 'volume' not in result:
        ### We dont error control cleanup
        net_out.write(
            'ERROR: Failed to attach volume on VM %s.'
            ' Response was %s\n' % (vm_id, result),
        )
        ### Adding clean up stuff
        return False

    net_out.write(
        'Volume %s successfully attached to VM %s.\n'
        % (volume_id, vm_id)
    )
    return True

def resize_volume(volume_id,volume_size,api,net_out):
    ### Send message out ###
    net_out.write(
        'Resize volume: %s to size %s' %
        (volume_id,volume_size),
    )
    ### Actually resize the volume
    request = {
        'id': volume_id,
        'size': volume_size
    }
    result = api.resizeVolume(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed to create job to resize EBS volume  %s. '
            ' Response was %s\n' %
            (volume_id, result),
        )
        return False

    result = wait_for_job(result['jobid'], api)
    if result == {}:
        net_out.write(
            'ERROR: Failed to create job to resize EBS volume  %s. '
            ' Response was %s\n' %
            (volume_id, result),
        )
        return False

    net_out.write('EBS Volume successfully resized.\n')
    return True


def delete_volume(volume_id,vm_id,api,net_out):

    ### Send message out ### 
    net_out.write(
        'Deleting volume: %s\n' %
        (volume_id), 
    )

    # Detach volumes
    request = {
        'id': volume_id,
    }
    result = api.detachVolume(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed job to detach volume on VM %s. '
            ' Response was %s\n' %
            (vm_id, result),
        )
        return False

    result = wait_for_job(result['jobid'], api)

    if result == {}:
        net_out.write(
            'ERROR: Failed to detach volume from VM %s.'
            ' Response was %s\n' % (vm_id, result),
        )
        return False

    # Check if Volumes are successfully detached
    counter = 0
    timeout = 60
    while counter < timeout:
        request = {
            'id': volume_id,
        }
        result = api.listVolumes(request)
        if result == {} or 'volume' not in result:
            net_out.write(
                'ERROR: Failed to detach volume from VM %s.'
                ' Response was %s\n' % (vm_id, result),
            )
            return False
        elif 'virtualmachineid' not in result['volume'][0]:
            net_out.write(
                'Volume successfully detached from VM.\n'
            )
            break

        counter += 1

        if counter == timeout:
            net_out.write(
                'ERROR: TimeOut. Failed to detach volume from VM %s.'
                ' Response was %s\n' % (vm_id, result),
            )
            return False
        time.sleep(1)

    # Delete volumes
    request = {
        'id': volume_id,
    }
    result = api.deleteVolume(request)

    ###print('Delete volume result\n')
    ###print(result)

    if result=={} or 'success' not in result:
        net_out.write(
            'ERROR:Failed to delete volume %s.' 
            'Response was %s\n' % (volume_id, result),
        )
        return False

    if result['success']:
        net_out.write(
            'Volume successfully deleted.\n'
        )
        return True
    else:
        net_out.write(
            'ERROR:Failed to delete volume %s.' 
            'Response was %s\n' % (volume_id, result),
        )
        return False

def start_vm(vm_id,api,net_out):
    # Start VM
    request = {'id': vm_id}
    result = api.startVirtualMachine(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed job to start VM  %s. '
            ' Response was %s\n' %
            (vm_id, result),
        )
        return False
    net_out.write('Starting VM...\n')

    result = wait_for_job(result['jobid'], api)

    if result == {} or 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Failed to start VM %s.'
            ' Response was %s\n' % (vm_id, result)
        )
        return False

    if 'password' in result['virtualmachine']:
        vm_password = result['virtualmachine']['password']
        net_out.write(
            'VM %s successfully started for the first time. ROOT password: %s.\n'
            % (vm_id, vm_password),
        )
        return vm_password
    else:
        net_out.write(
            'VM %s successfully (re)started.\n'
            % (vm_id),
        )
        return True


def stop_vm(vm_id,api,net_out):
    # Stop VM
    request = {
        'id': vm_id,
    }
    stop_result = api.stopVirtualMachine(request)
    net_out.write('Stopping VM...\n')

    if stop_result == {} or 'jobid' not in stop_result:
        net_out.write(
            'ERROR: Failed job to stop VM %s. '
            ' Response was %s\n' %
            (vm_id, result),
        )
        return False
    net_out.write('Stopping VM...\n')

    result = wait_for_job(stop_result['jobid'], api)
    if result == {} or 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Failed to stop VM %s.'
            ' Response was %s\n' % (vm_id, result)
        )
        return False
    ### We still wait for the VM to be in actual stopped stated ###
    if wait_stop(vm_id, api):
        net_out.write('VM successfully stopped.\n')
        return True
    else:
        net_out.write(
            'ERROR: VM %s failed to stop within the timeout. JobID %s\n'
            % (vm_id, stop_result)
        )
        return False

def deploy_vm_iso(
    vm_name,
    zone_id,
    network_id,
    domain_id,
    account_name,
    net_out,
    iso_id,
    api,
    disk_offering_name='Small',
    offering_name='Medium Instance',
    startvm='False'):

    net_out.write(
        'Deploying VM %s to offering %s \n' %
        (vm_name, offering_name)
    )

    ### Get the service offering ID ###
    request = {
        'listall': 'True',
        'name': offering_name,
    }
    result = api.listServiceOfferings(request)
    if result == {} or 'serviceoffering' not in result:
        output(
            message='Could not find service offering.',
        )
        return False
    service_offering_id = result['serviceoffering'][0]['id']
    service_offering_name = result['serviceoffering'][0]['displaytext']
    net_out.write(
        'Using service offering %s with ID %s\n' %
        (service_offering_name, service_offering_id),
    )

    ### Get the disk offering id ###

    request = {}
    result = api.listDiskOfferings(request)

    for disk in result['diskoffering']:
        if disk['name'] == disk_offering_name:
            disk_offering_id = disk['id']

    # Check if disk offering exists
    if disk_offering_id == '':
        net_out.write(
            'ERROR: Disk offering %s not found' % disk_offering_name
        )
        return False

    ### Actually try to deploy the vm
    request = {
        'serviceofferingid': service_offering_id,
        'templateid': iso_id,
        'zoneid': zone_id,
        'networkids': network_id,
        'name': vm_name,
        'displayname': vm_name,
        'startvm': 'false',
        'domainid': domain_id,
        'account': account_name,
        'diskofferingid': disk_offering_id,
    }

    result = api.deployVirtualMachine(request)

    if result == {} or 'jobid' not in result:
        net_out.write(
            'ERROR: Failed to create job to deploy VM on network %s. '
            ' Response was %s\n' %
            (network_id, result),
        )
        return False

    net_out.write('Deploying VM on network %s.\n' % network_id)

    result = wait_for_job(result['jobid'], api)

    if result == {} or 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Failed to create VM on network %s. Response was %s\n' %
            (network_id, result),
        )
        return False

    vm_id = result['virtualmachine']['id']
    net_out.write(
        'VM %s successfully deployed on network %s.\n'
        % (vm_id, network_id),
    )
    return vm_id


def deploy_vm(
    vm_name,
    zone_id,
    network_id,
    domain_id,
    account_name,
    net_out,
    template_id,
    api,
    ip_address='',
    offering_name='Medium Instance',
    startvm='False'):

    net_out.write(
        'Deploying VM %s to offering %s \n' %
        (vm_name, offering_name)
    )

    ### Get the service offering ID ###
    request = {
        'listall': 'True',
        'name': offering_name,
    }
    result = api.listServiceOfferings(request)
    if result == {} or 'serviceoffering' not in result:
        output(
            message='Could not find service offering.',
        )
        return False
    service_offering_id = result['serviceoffering'][0]['id']
    service_offering_name = result['serviceoffering'][0]['displaytext']
    net_out.write(
        'Using service offering %s with ID %s\n' %
        (service_offering_name, service_offering_id),
    )

    ### Get the template name ###
    ##print('My Template ID %s\n' % template_id)
    request = {
        'templatefilter': 'executable',
        'zoneid': zone_id,
        'id': template_id,
    }
    result = api.listTemplates(request)
    if result == {} or 'template' not in result:
        net_out.write(
            'Not able to get template name for template id %s\n Result was %s' %
            (template_id, result),
        )
        return False
    template_name = result['template'][0]['name']
    net_out.write(
        'Template %s has ID %s. \n' %
        (template_name,template_id)
    )

    ### Actually try to deploy the vm
    request = {
        'serviceofferingid': service_offering_id,
        'templateid': template_id,
        'zoneid': zone_id,
        'networkids': network_id,
        'name': vm_name,
        'displayname': vm_name,
        'startvm': 'false',
        'domainid': domain_id,
        'account': account_name,
    }
    # We add IP address to request if specified
    if ip_address: 
        net_out.write('IP address %s specified\n' % ip_address)
        request['ipaddress']=ip_address
    result = api.deployVirtualMachine(request)

    if result == {} or 'jobid' not in result:
        net_out.write(
            'ERROR: Failed to create job to deploy VM on network %s. '
            ' Response was %s\n' %
            (network_id, result),
        )
        return False

    net_out.write('Deploying VM on network %s.\n' % network_id)

    result = wait_for_job(result['jobid'], api)

    if result == {} or 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Failed to create VM on network %s. Response was %s\n' %
            (network_id, result),
        )
        return False

    vm_id = result['virtualmachine']['id']
    net_out.write(
        'VM %s successfully deployed on network %s.\n'
        % (vm_id, network_id),
    )
    return vm_id


def scale_vm(vm_id,offering_name,api,net_out):
    net_out.write(
        'Scaling VM %s to offering %s \n' %
        (vm_id, offering_name)
    )
    request = {
        'listall': 'True',
        'name': offering_name,
    }
    result = api.listServiceOfferings(request)

    if result == {} or 'serviceoffering' not in result:
        output(
            message='Could not find service offering.',
        )
        return False
    service_offering_id = result['serviceoffering'][0]['id']
    service_offering_name = result['serviceoffering'][0]['displaytext']

    net_out.write(
        'Using service offering %s with ID %s\n' %
        (service_offering_name, service_offering_id)
    )

    ### Check the virtual machine
    request = {
        'id': vm_id,
    }
    result = api.listVirtualMachines(request)

    if result == {} or 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Failed to find VM with id %s.'
            ' Response was %s\n' % (vm_id, result)
        )
        return False
    vm=result['virtualmachine'][0]

    net_out.write('Virtual machine is dynamically scalable: %s\n' % vm['isdynamicallyscalable'])

    request = {
        'id': vm_id,
        'serviceofferingid': service_offering_id,
    }
    result=api.scaleVirtualMachine(request)
    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed to resize vm %s. '
            ' Response was %s\n' %
            (vm_id, result),
        )
        return False
    
    result = wait_for_job(result['jobid'], api)
    ##print('Scale result\n')
    ##pprint(result)
    if result=={} or 'virtualmachine' not in result:
        net_out.write(
            'ERROR:Failed to resize vm %s.'
            'Response was %s\n' % (vm_id, result),
        )
        return False

    ###print ('service offering id we get %s\n'%  result['virtualmachine']['serviceofferingid'])
    ###print ('service offering id we were supposed to get  %s\n'%  service_offering_id)

    if result['virtualmachine']['serviceofferingid']== service_offering_id:
        net_out.write(
            'VM %s successfully resized to offering %s.\n' %
            (vm_id,service_offering_id)
        )
        return True
    else:
        net_out.write(
            'Failed to resize VM %s.'
            'Response was %s\n' % (volume_id, result),
        )
        return False

def rebuild_vm(vm_id,api,net_out):
    net_out.write(
        'Rebuilding VM %s from template \n' % vm_id
    )
    request = {
        'virtualmachineid': vm_id,
    }

    result=api.restoreVirtualMachine(request)

    if result['restorevmresponse'] == {} or 'jobid' not in result['restorevmresponse']:
        net_out.write(
            'ERROR: Failed to rebuild vm %s. '
            ' Response was %s\n' %
            (vm_id, result),
        )
        return False
    result = wait_for_job(result['jobid'], api)
    if 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Failed to use job to rebuild vm %s. '
            ' Response was %s\n' %
            (vm_id, result),
        )
        return False
    vm_id=result['virtualmachine']['id']
    return vm_id


def reset_password(vm_id,api,net_out):
    net_out.write(
        'Resetting password for vm %s\n' % vm_id
    )
    ## First we stop the vm ##
    request = {
        'id': vm_id,
    }
    stop_result = api.stopVirtualMachine(request)
    net_out.write('Stopping VM...\n')

    if wait_stop(vm_id, api):
        net_out.write('VM successfully stopped.\n')

    else:
        net_out.write(
            'ERROR: VM %s failed to stop: %s\n'
            % (vm_id, stop_result)
        )
        return False

    request = {
        'id': vm_id,
    }
    result=api.resetPasswordForVirtualMachine(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed to isse job to reset password %s. '
            ' Response was %s\n' %
            (vm_id, result),
        )
        ### We dont error control cleanup
        return False
    result = wait_for_job(result['jobid'], api)
    if 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Failed to isse job to reset password %s. '
            ' Response was %s\n' %
            (vm_id, result),
        )
        return False
    password=result['virtualmachine']['password']
    return password

def add_nic(vm_id,network_id,ip_address,api,net_out):
    net_out.write('Add additional nic to vm %s\n' %vm_id)

    request = {
        'networkid': network_id,
        'virtualmachineid': vm_id,
        'ipaddress': ip_address,
    }
    result = api.addNicToVirtualMachine(request)
    net_out.write(result)
    output(result)
    net_out.write('Adding NIC 2 to VM...\n')

    if result == {} or 'jobid' not in result:
        net_out.write(
            'ERROR: Failed job to add NIC '
            ' Response was %s\n' %
            (result),
        )
        return False
    result = wait_for_job(result['jobid'], api)
    net_out.write(result)
    output(result)
    if 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Failed job to add NIC '
            ' Response was %s\n' %
            (vm_id, result),
        )
        return False
    nics=result['virtualmachine']['nic']
    pprint(nics)
    net_out.write('NIC 2 successfully added to the VM.\n')

    for nic in nics:
        if nic['networkid']==network_id:
            nic_id=nic['id']
            net_out.write(
                'Network NIC on network %s has ID %s\n' %
                (network_id,nic_id)
            )
            return nic_id 

    net_out.write(
        'ERROR: Failed to add NIC to network. Did not find NIC on network %s\n'
        'Found NICS %s\n' %
        (network_id, nics),
    )

def get_nic(vm_id,network_id,ip_address,api,net_out):
    
    #Get NICs
    request = {
        'virtualmachineid':vm_id,
    }
    result = api.listNics(request)
   
    print (result)
    
    if result == {} or 'nic' not in result:
        net_out.write(
            'ERROR: Failed Get iis or NICS. '
            ' Response was %s\n' %
            (result),
        )
        return False
    nics=result['nic']
    
    for nic in nics:
        if nic['networkid']==network_id:
            nic_id=nic['id']
            net_out.write(
                'Network NIC on network %s has ID %s\n' %
                (network_id,nic_id)
            )
            return nic_id

    net_out.write(
        'ERROR: Failed to add NIC to network. Did not find NIC on network %s\n'
        'Found NICS %s\n' %
        (network_id, nics),
    )
    
   


def create_egress(network_id,api,net_out):
#Set egress firewall for VM to ports 80/tcp and 53/udp

    net_out.write(
        'Setting egress FW rules for port 80 and 53 network %s\n' % network_id
    )

    request = {
       'networkid': network_id,
       'listall': True,
    }

    result = api.listEgressFirewallRules(request)

    firewall_rules={}

    if result == {} or 'firewallrule' not in result:
        egress_ids = [] 
        net_out.write('No FW rules found\n')
    else:
        firewall_rules = result['firewallrule'] 
        egress_ids = [] 
        net_out.write('FW rules found\n')
        net_out.write(firewall_rules)


    for port in ['80', '53']:
        if port == '53':
            protocol = 'UDP'
        else:
            protocol = 'TCP'
        # We check if the FW rule exists 
        if firewall_rules != {} :
            for firewall_rule in firewall_rules:
                if firewall_rule['startport'] == port and firewall_rule['protocol'] == protocol:
                    myegress_id = firewall_rule['id']
                    net_out.write('egress id: %s\n'  % firewall_rule['id'] )
                    egress_ids.append(firewall_rule['id'])
                    net_out.write ( 
                        'Firewall rule for network %s and port %s already exists \n is: %s' 
                        % ( network_id, port, firewall_rule['id'] )
                    )
                else:       
                    request = {
                        'networkid': network_id,
                        'protocol': protocol,
                        'startport': port,
                    }
                    result = api.createEgressFirewallRule(request)

                    # ERROR_HANDLING
                    if result == {} or 'jobid' not in result.keys():
                        net_out.write(
                            'ERROR: Failed job to create egress firewall rule.'
                            ' Response was %s\n' %
                            result,
                        )
                        return False

                    result = wait_for_job(result['jobid'], api)
                    if result == {}:
                        net_out.write(
                            'ERROR: Failed to create egress firewall rule.'
                            'Response was %s\n' % result,
                        )
                        return False

                    egress_ids.append(firewall_rule['id'])

                    net_out.write(
                        'egress firewall rule %s successfully created on network %s '
                        'for port: %s/%s.\n'
                        % (firewall_rule['id'], network_id, port, protocol)
                    )

                    # Wait for the new Rules to apply
                    time.sleep(5)

    # We return the egress firewall ids
    return egress_ids

def remove_egress(egress_ids,api,net_out):
    net_out.write(
        'Removing egress FW rules %s\n' % egress_ids
    )
    # Remove egress firewall rules
    for egress_id in egress_ids:
        request = {'id': egress_id}
        result = api.deleteEgressFirewallRule(request)
        if result == {} or 'jobid' not in result:
            net_out.write(
                'ERROR: Failed to delete egress firewall rule on network %s.'
                'Response was %s\n' % (egress_id, result)
            )
            return False
        result = wait_for_job(result['jobid'], api)
        if result == {} or result['success'] == 'False':
            net_out.write(
                'ERROR: Failed to delete egress firewall rule on network %s.'
                'Response was %s\n' %
                (egress_id, result),
            )
            return False
        net_out.write(
            'The egress firewall rule has been successfully removed.\n'
        )
    # Everything has been successfull (if we get here)
    return True

def get_public_ip(network_id,api,net_out):
    net_out.write(
        'Acquiring public IP for network %s.\n' % network_id
    )
    #Acquire new Public IP
    request = {
        'networkid': network_id,
    }
    newIP_result = api.associateIpAddress(request)
    net_out.write('Acquiring new Public IP address...\n')

    if newIP_result == {}:
        net_out.write(
            'ERROR: Failed to acquire new IP to the network %s. Response was %s\n' %
            (network_id, newIP_result),
        )
        return False

    ipaddress_id = newIP_result['id']
    
    net_out.write('Public IP address with id %s sucessfully acquired.\n' %
        (ipaddress_id),
    )

    ## Update network ##
    request = {
        'id': network_id,
    }
    result = api.updateNetwork(request)
    net_out.write('Updating network...\n')
    
    if result == {}:
        net_out.write(
            'ERROR: Failed to update network. Response was %s\n' %
            (result),
        )
        return False

    net_out.write('Network updated\n')
    return ipaddress_id

def release_public_ip(ipaddress_id,network_id,api,net_out):
    net_out.write('Release public IP with ID: %s' % ipaddress_id)

    #Get some more info from the IP address
    request = {
        'id': ipaddress_id,
        'listall': 'True',
    }
    result=api.listPublicIpAddresses(request)
    if result == {} or 'ipaddress' not in result:
        net_out.write(
            'ERROR: Failed to find Public IP from the network %s. Response was %s\n' %
            (network_id, result),
        )
        return False
    ipaddress=result['publicipaddress'][0]['ipaddress']
    net_out.write('Public IP address %s\n' % ipaddress)

    #Release Public IP
    request = {
        'id': ipaddress_id,
    }
    releaseIP_result = api.disassociateIpAddress(request)
    net_out.write('Releasing Public IP address...\n')
   
    if releaseIP_result == {}:
        net_out.write(
            'ERROR: Failed to  release Public IP from the network %s. Response was %s\n' %
            (network_id, result),
        )
        return False

    net_out.write('Public IP address sucessfully released...\n')
    
   #Update network
    request = {
        'id': network_id,
    }
    result = api.updateNetwork(request)
    net_out.write('Updating network...\n')
    
    if result == {}:
        net_out.write(
            'ERROR: Failed to update network. Response was %s\n' %
            (result),
        )
        return False

    net_out.write('Network updated\n')
    return True

def enable_nat(ipaddress_id,vm_id,network_id,api,net_out):
    net_out.write(
        'Enabling NAT for IP %s to vm %s on network %s\n'
        %  (ipaddress_id,vm_id,network_id)
    )
    #Enable NAT
    request = {
        'ipaddressid': ipaddress_id,
        'virtualmachineid': vm_id,
        'networkid': network_id,
    }
    result = api.enableStaticNat(request)
    net_out.write('Enable Static NAT...\n')
    
    if result == {} or 'success' not in result:
        net_out.write(
            'ERROR: Failed to enable NAT Response was %s\n' %
            (result),
        )
        return False

    net_out.write('Success result %s\n' % result['success'] )
    net_out.write('NAT enabled\n')
    return True

def disable_nat(ipaddress_id,api,net_out):
    net_out.write(
        'Disabling static NAT for IP %s\n'
        %  (ipaddress_id)
    )
    #Disable  NAT
    request = {
        'ipaddressid': ipaddress_id,
    }
    result = api.disableStaticNat(request)
        
    if result == {}:
        net_out.write(
            'ERROR: Failed to disable NAT Response was %s\n' %
            (result),
        )
        return False

    net_out.write('NAT disabled\n')
    return True

def add_firewall_rule(ipaddress_id,network_id,protocol,cidr_list,start_port,end_port,api,net_out):
    net_out.write('Adding FW Rule ... \n')
    # Get details of the IP address #
    request = {
        'id': ipaddress_id,
        'listall': 'True',
    }
    result=api.listPublicIpAddresses(request)
    if result == {} or 'publicipaddress' not in result:
        net_out.write(
            'ERROR: Failed to find Public IP from the network %s. Response was %s\n' %
            (network_id, result),
        )
        return False
    ipaddress=result['publicipaddress'][0]['ipaddress']

    net_out.write(
            'FW rule: %s -> %s-%s / %s -> % s\n' %
            (cidr_list,start_port,end_port,protocol,ipaddress)
        )

    #Add Firewall Rule
    request = {
        'ipaddressid': ipaddress_id,
        'protocol': protocol,
        'cidrlist': cidr_list,
        'startport': start_port,
        'endport': end_port,
    }
    result = api.createFirewallRule(request)
    net_out.write('Adding Firewall Rule...\n')
    
    if result == {} or 'jobid' not in result:
        net_out.write(
            'ERROR: Failed to add Firewall Rule. Response was %s\n' %
            (result),
        )
        return False
    
    result = wait_for_job(result['jobid'], api)
    if result == {} or 'firewallrule' not in result:
        net_out.write(
            'ERROR: Failed to add Firewall Rule. Response was %s\n' %
            (result),
        )
        return False
   
    fwrule_id=result['firewallrule']['id']
    net_out.write('Firewall Rule %s added\n' % fwrule_id)
    return fwrule_id

    

def delete_firewall_rule(fwrule_id,api,net_out):
    net_out.write('Removing FW Rule ... \n')
    #Delete Firewall Rule
    request = {
        'id': fwrule_id,
    }
    result = api.deleteFirewallRule(request)
        
    if result == {}:
        net_out.write(
            'ERROR: Failed to delete Firewall rule. Response was %s\n' %
            (result),
        )
        return False

    net_out.write('Firewall rule deleted\n')
    return True


def add_portforwarding(network_id,vm_id,api,net_out):
    net_out.write('Adding SSH port_forwarding ...\n') 
    # Get public IP ID of isolated networks
    request = {
        'associatednetworkid': network_id,
        'listall': 'True',
        }
    result = api.listPublicIpAddresses(request)

    if result == {} or 'publicipaddress' not in result:
        net_out.write(
            '\n ERROR: Failed to obtain public IP of the network\n'
        )
        return False

    for ip in result['publicipaddress']:
        ip_id = (ip['id'])
        ip_address = ip['ipaddress']

    # Set port forwarding rule (including firewall)
    # for VM -> port 22 (SSH access)
    # Set variables
    protocol = 'TCP'
    public_port = str(22000+random.randint(1,1000))
    private_port = '22'

    # N.B: if deploying more than 1 machine per network,
    # public_port must be changed
    request = {
        'ipaddressid': ip_id,
        'privateport': private_port,
        'publicport': public_port,
        'virtualmachineid': vm_id,
        'protocol': protocol,
    }
    result = api.createPortForwardingRule(request)

    # ERROR_HANDLING
    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed job to create port forwarding rule.'
            ' Response was %s\n' %
            result,
        )
        return False

    result = wait_for_job(result['jobid'], api)

    if result == {}:
        net_out.write(
            'ERROR: Failed to create port forwarding rule.'
            ' Response was %s\n' % result,
        )
        return False

    portforward_id = result['portforwardingrule']['id']

    net_out.write(
        'Port forwarding rule %s successfully created on network %s '
        'from %s private port %s to public port %s.\n'
        % (portforward_id, network_id, protocol, private_port, public_port),
    ) 

    port_forwarding_data={}
    port_forwarding_data['IP']=ip_address
    port_forwarding_data['public_port']=public_port
    port_forwarding_data['portforward_id']=portforward_id
    return port_forwarding_data

def remove_portforwarding(portforward_id,api,net_out):
    # Remove port fowarding rule
    request = {'id': portforward_id}
    result = api.deletePortForwardingRule(request)
    if result == {} or 'jobid' not in result:
        net_out.write(
            'ERROR: Failed to delete port forwarding rule %s.'
            'Response was %s\n' %
            (portforward_id, result),
        )
        return False   

    result = wait_for_job(result['jobid'], api)
    if result == {} or 'success' not in result:
        net_out.write(
            'ERROR: Failed to delete port forwarding rule %s.'
            'Response was %s\n' %
            (portforward_id, result),
        )
        return False
    net_out.write(
        'The port forwarding rule has been successfully removed.\n'
        'Result: %s.\n' %
         result['success'] 
    )
    return True

def delete_snapshot(snapshot_id,api,net_out):  
### First we get add data from the snapshot_id
    request = {
        'id': snapshot_id,
        'listall': 'True',
    }
    result = api.listSnapshots(request)
    if result == {} or 'snapshot' not in result:
        net_out.write(
            'ERROR: Failed to find snapshot with id %s.'
            ' Response was %s\n' % (snapshot_id, result)
        )
        return False
    snapshot=result['snapshot'][0]
    ##print('Trying to delete snapshot %s with ID %s\n' % (snapshot['name'],snapshot['id']))
    net_out.write(
        'Trying to delete snapshot %s with ID %s\n' % (snapshot['name'],snapshot['id'])
    )
### We try to delete the actual snapshot
    request = {
        'id': snapshot_id
    }

    result = api.deleteSnapshot(request)
    if result == {} or 'jobid' not in result:
        net_out.write(
            'ERROR: Failed to delete snapshot with id %s.'
            ' Response was %s\n' % (snapshot_id, result)
        )
        return False

    result = wait_for_job(result['jobid'], api)

    if result == {} or 'success' not in result:
        net_out.write(
            'ERROR: Failed to delete snapshot with id %s.'
            ' Response was %s\n' % (snapshot_id, result)
        )
        return False

    net_out.write(
        'Deleted snapshot %s with ID %s\n' % (snapshot['name'],snapshot['id'])
    )
    return True
    

def create_snapshot_schedule(volume_id,schedule,api,net_out):  
    net_out.write('Creating Snapshot Schedule... \n')
    request = {
        'listall': 'True',
        'id': volume_id,
    }
    result = api.listVolumes(request)
    if result == {} or 'volume' not in result:
        net_out.write(
            'ERROR: Failed to find volume  %s.'
            ' Response was %s\n' % (volume_id, result)
        )
        return False
    volume=result['volume']
    volume_id=volume[0]['id']
    volume_name=volume[0]['name']

### Define the policies based on the input
### The following schedules are valid ###
### HOURLY: hourly at random minute, retain 5 ###
### DAILY: Dailiy at random hour between 1 and 5  at random minute, retain 2 ###

    if schedule == 'HOURLY':
        interval_type=schedule
        max_snaps='5'
        execute_time=str(random.randint(10,59))
    elif eschedule == 'DAILY':
        interval_type=schedule
        max_snaps='2'
        execute_time='0'+str(random.randint(1,5))
    else:
        net_out('ERROR: Unrecognized schedule %s\n' % schedule)
        return False

    time_zone='CET'
### Create the schedule
    request = {
        'volumeid': volume_id,
        'intervaltype': interval_type,
        'maxsnaps': max_snaps,
        'schedule': execute_time,
        'timezone': time_zone,
    }
    if result == {} or 'snapshotpolicy' not in result:
        net_out.write(
            'ERROR: Failed to create snapshot policy %s. '
            ' Response was %s\n' %
            (schedule, result),
        )
        return False

    snapshotpolicy_id=result['snapshotpolicy']['id']

def snapshot_volume(volume_id,api,net_out):  
### We get the volume data
    request = {
        'listall': 'True',
        'id': volume_id,
    }

    result = api.listVolumes(request)
    if result == {} or 'volume' not in result:
        net_out.write(
            'ERROR: Failed to find ROOT volume for vm %s.'
            ' Response was %s\n' % (volume_id, result)
        )
        return False
    volume=result['volume']
    volume_id=volume[0]['id']
    volume_name=volume[0]['name']

### Take a snapshot of the volume
    request = {
        'volumeid': volume_id,
    }
    result = api.createSnapshot(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed to create job to take snapshot of volume %s. '
            ' Response was %s\n' %
            (volume_name, result),
        )
        return False

    result = wait_for_job(result['jobid'], api)

    if result == {} or result['snapshot']['volumeid'] != volume_id:
        net_out.write(
            'ERROR: Failed to take snapshot of volume %s.'
            ' Response was %s\n' % (volume_name, result),
        )
        return False

    # Define snapshot ID
    snapshot_id = result['snapshot']['id']
    net_out.write(
        'snapshot of volume %s created. ID %s\n' % (volume_name,snapshot_id)
    )
    return snapshot_id


def snapshot_rootvol(vm_id,api,net_out):  
### First we get all date from the vm_id
    net_out.write('Taking a snapshot of rootvol ...')
    request = {
        'id': vm_id,
    }
    result = api.listVirtualMachines(request)

    if result == {} or 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Failed to find VM with id %s.'
            ' Response was %s\n' % (vm_id, result)
        )
        return False
    vm=result['virtualmachine']

### Find the actual root volume
    request = {
        'virtualmachineid': vm_id,
        'listall': 'True',
        'type':  'ROOT',
    }

    result = api.listVolumes(request)
    if result == {} or 'volume' not in result:
        net_out.write(
            'ERROR: Failed to find ROOT volume for vm %s.'
            ' Response was %s\n' % (vm['name'], result)
        )
        return False
    volume=result['volume']
    volume_id=volume[0]['id']
    volume_name=volume[0]['name']

### Take a snapshot of the volume
    request = {
        'volumeid': volume_id,
    }
    result = api.createSnapshot(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed to create job to take snapshot of volume %s. '
            ' Response was %s\n' %
            (volume_name, result),
        )
        return False
    
    result = wait_for_job(result['jobid'], api)

    if result == {} or result['snapshot']['volumeid'] != volume_id:
        net_out.write(
            'ERROR: Failed to take snapshot of volume %s.'
            ' Response was %s\n' % (volume_name, result),
        )
        return False

    # Define snapshot ID
    snapshot_id = result['snapshot']['id']
    net_out.write(
        'snapshot of volume %s created. ID %s\n' % (volume_name,snapshot_id)
    )
    return snapshot_id

def delete_template(template_id,api,net_out):
    ### First we get add data from the template_id
    request = {
        'id': template_id,
        'templatefilter': 'executable',
        'listall': 'True',
    }
    result = api.listTemplates(request)
    ##print('template result\n')
    ##print(result)
    if result == {} or 'template' not in result:
        net_out.write(
            'ERROR: Failed to find template with id %s.'
            ' Response was %s\n' % (template_id, result)
        )
        return False
    template=result['template'][0]
    template_name=result['template'][0]['name']

    ##print('Trying to delete template %s with ID %s\n' % (template_name,template_id) )
    net_out.write(
        'Trying to delete template %s with ID %s\n' % (template_name,template_id)
    )
    ### We try to delete the actual template
    request = {
        'id': template_id
    }

    result = api.deleteTemplate(request)
    if result == {} or 'jobid' not in result:
        net_out.write(
            'ERROR: Failed to delete template %s with ID %s.'
            ' Response was %s\n' % (template_name,template_id, result)
        )
        return False
    result = wait_for_job(result['jobid'], api)
    if result=={} or 'success' not in result:
        net_out.write(
            'ERROR: Failed to delete template %s.'
            'Response was %s\n' % (template_id, result),
        )
        return False

    if result['success']:
        net_out.write(
            'Template successfully deleted.\n'
            'Displaytext: %s.\n' %
            result['success']
        )
        return True
    else:
        net_out.write(
            'ERROR:Failed to delete template %s.'
            'Response was %s\n' % (template_id, result),
        )
        return False

    net_out.write(
        'Deleted template %s with ID %s\n' % (template_name,template_id)
    )
    return True

def attach_iso(iso_id,vm_id,api,net_out):
    # First we get the name of the ISO
    request = {
        'id': iso_id,
        'listall': 'True',
        'isofilter': 'self',
    }
    result = api.listIsos(request)
    if result == {} or 'ISO' not in result:
        net_out.write(
            'ERROR: Failed to find ISO with id %s.'
            ' Response was %s\n' % (template_id, result)
        )
        return False
    iso=result['iso'][0]
    iso_name=result['iso'][0]['name']

    net_out.write(
        'Trying to attach iso %s with ID %s\n' % (iso_name,iso_id)
    )

    ### We try to attach the ISO
    request = {
        'id': iso_id,
        'virtualmachineid': vm_id,
    }
    result = api.attachIso(request)

    if result == {} or 'jobid' not in result.keys():
        ### We dont error control cleanup
        net_out.write(
            'ERROR: Failed to create job to attach ISO %s to VM %s. '
            ' Response was %s\n' % (iso_id, vm_id, result),)
        ### Adding clean up stuff
        return False

    result = wait_for_job(result['jobid'], api)
    if result == {} or 'virtualmachine' not in result:
        ### We dont error control cleanup
        net_out.write(
            'ERROR: Failed to attach ISO %s to VM %s.'
            ' Response was %s\n' % (iso_id, vm_id, result),
        )
        ### Adding clean up stuff
        return False

    net_out.write(
        'Volume %s successfully attached to VM %s.\n'
        % (volume_id, vm_id)
    )
    return True


def detach_iso(vm_id,api,net_out):
    net_out.write('Trying to detach ISOs from vm_id: %s\n' % vm_id)
    ### First we check there is an ISO attached
    request = {
        'id': vm_id,
    }
    result = api.listVirtualMachines(request)

    if result == {} or 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Failed to find VM with id %s.'
            ' Response was %s\n' % (vm_id, result)
        )
        return False

    virtual_machine=['virtualmachine'][0]
    vm_name=virtualmachine['name']

    if 'isoid' not in virtualmachine:
        net_out.write(
            'ERROR: Failed to find ISO attached to vm  %s with id %s.\n' %
            (vm_name, vm_id, result)
        )
        return False
    else: 
        net_out.write(
            'Currently attached ISO id %s.\n' %
            (iso_id)
        )

    ## We execute the command ###
    request = {
        'virtualmachineid': vm_id,
    }
    result = api.detachIso(request)

    if result == {} or 'jobid' not in result.keys():
        ### We dont error control cleanup
        net_out.write(
            'ERROR: Failed to create job to detach ISO from VM %s. '
            ' Response was %s\n' % (vm_id, result),)
        ### Adding clean up stuff
        return False

    result = wait_for_job(result['jobid'], api)
    if result == {} or 'virtualmachine' not in result:
        ### We dont error control cleanup
        net_out.write(
            'ERROR: Failed to detach ISO from VM %s.'
            ' Response was %s\n' % (iso_id, vm_id, result),
        )
        ### Adding clean up stuff
        return False

    net_out.write(
        'Volume %s successfully attached to VM %s.\n'
        % (volume_id, vm_id)
    )
    return True


def delete_iso(iso_id,api,net_out):
    ### First we get add data from the iso_id
    request = {
        'id': iso_id,
        'listall': 'True',
        'isofilter': 'self',
    }
    result = api.listIsos(request)
    if result == {} or 'ISO' not in result:
        net_out.write(
            'ERROR: Failed to find ISO with id %s.'
            ' Response was %s\n' % (iso_id, result)
        )
        return False
    iso=result['iso'][0]
    iso_name=result['iso'][0]['name']

    net_out.write(
        'Trying to delete iso %s with ID %s\n' % (iso_name,iso_id)
    )
    ### We try to delete the actual ISO
    request = {
        'id': iso_id
    }
    result = api.deleteIso(request)
    if result == {} or 'jobid' not in result:
        net_out.write(
            'ERROR: Failed to delete ISO %s with ID %s.'
            ' Response was %s\n' % (iso_name,iso_id, result)
        )
        return False

    result = wait_for_job(result['jobid'], api)
    if result=={} or 'success' not in result:
        net_out.write(
            'ERROR: Failed to delete ISO %s.'
            'Response was %s\n' % (iso_id, result),
        )
        return False

    if result['success']:
        net_out.write(
            'ISO successfully deleted.\n'
            'Displaytext: %s.\n' %
            result['success']
        )
        return True
    else:
        net_out.write(
            'ERROR:Failed to delete ISO %s.'
            'Response was %s\n' % (iso_id, result),
        )
        return False

def create_template_fromrootvol(vm_id,ostype_id,domain_id,account_name,api,net_out):  
    net_out.write('Creating template from rootvol of vm %s\n' % vm_id)
    request = {
        'virtualmachineid': vm_id,
        'type': 'ROOT',
        'listall': 'True',
    }
    result = api.listVolumes(request)
    if result == {} or 'volume' not in result:
        net_out.write(
            'ERROR: Failed to find snapshot with id %s.'
            ' Response was %s\n' % (snapshot_id, result)
        )
        return False

    volume=result['volume'][0]
    volume_name=volume['name']
    volume_id=volume['id']

    net_out.write('volume_name: %s\n' % volume_name)
    net_out.write('volume_id: %s\n' % volume_id)

    ### Try to create the actual template
    testtemplatename=account_name+'-test-template'+str(random.randint(1,1000))

    request={
        'displaytext': testtemplatename,
        'name': testtemplatename,
        'ostypeid': ostype_id,
        'volumeid': volume_id,
        'account': account_name,
        'domainid': domain_id,
        'ispublic': 'True',
        'isfeatured': 'True',
    }
    result = api.createTemplate(request)

    ##print('Create template result\n')
    ##print(result)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed to create job to create template from snapshot %s.\n'
            'Response was %s\n' %
            (snapshot_id, result),
        )
        return False

    result = wait_for_job(result['jobid'], api)

    if result == {} or 'template' not in result:
        net_out.write(
            'ERROR: Job to create template from rootvol %s. '
            ' Response was %s\n' %
            (volume_id, result),
        )
        return False

    # Return template id
    template_id = result['template']['id']
    net_out.write(
        'Template %s from rootvol %s created. ID %s\n' % (testtemplatename,volume_name,template_id)
    )
    return template_id




def create_template_fromsnap(snapshot_id,ostype_id,domain_id,account_name,api,net_out):  
    net_out.write('Creating template from snapshot id %s\n' % snapshot_id)
    request = {
        'id': snapshot_id,
        'account': account_name,
        'domainid':  domain_id,
    }

    result = api.listSnapshots(request)
    if result == {} or 'snapshot' not in result:
        net_out.write(
            'ERROR: Failed to find snapshot with id %s.'
            ' Response was %s\n' % (snapshot_id, result)
        )
        return False

    snapshot=result['snapshot'][0]
    snapshot_name=snapshot['name']

    ### Try to create the actual template

    ###testtemplatename=account_name+'-test-template'+str(random.randint(1,1000))
    testtemplatename='%s-test-template-%s' % ( account_name, str(random.randint(1,100)) )

    request={
        'displaytext': testtemplatename,
        'name': testtemplatename,
        'ostypeid': ostype_id,
        'snapshotid': snapshot_id,
        'account': account_name,
        'domainid': domain_id,
        'ispublic': 'True',
        'isfeatured': 'True',
    }
    result = api.createTemplate(request)

    ##print('Create template result\n')
    ##print(result)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed to create job to create template from snapshot %s.\n'
            'Response was %s\n' %
            (snapshot_id, result),
        )
        return False

    ##print('Job to create template\n')
    ##print(result['jobid'])

    result = wait_for_job(result['jobid'], api)

    if result == {} or 'template' not in result:
        net_out.write(
            'ERROR: Job to create template from snapshot %s. '
            ' Response was %s\n' % 
            (snapshot_id, result),
        )
        return False

    # Return template id
    template_id = result['template']['id']
    net_out.write(
        'Template from snapshot %s created. ID %s\n' % (template_id,snapshot_id)
    )
    return template_id

    

def migrate_vm(vm_id,api,net_out):  
    ### Migrate Virtual Machine ###

    ### First find out the current hostname ### 
    request = {
        'id': vm_id,
    }
    result = api.listVirtualMachines(request)

    if result == {} or 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Failed to find VM with id %s.'
            ' Response was %s\n' % (vm_id, result)
        )
        return False
    
    vm_name=result['virtualmachine'][0]['name']
    vm_current_hostid=result['virtualmachine'][0]['hostid']
    vm_current_hostname=result['virtualmachine'][0]['hostname']

    net_out.write(
        'vm %s currently on host %s \n' %
        (vm_name, vm_current_hostname)
    )

    ### List the available hosts ###
    request = {
       'hypervisor': 'VMware',
       'zoneid': zone_id,
    } 
    result = api.listHosts(request)
    if result == {} or 'host' not in result:
        net_out.write(
            'ERROR: Failed to find VMware hosts in zone id  %s'
            ' Response was %s\n' % (zone_id,result)
        )
        return False

    available_hosts=result['host']

    candidate_hostid='Null'
    for host in available_hosts:
        if host['id'] != vm_current_hostid:
            candidate_hostname=host['name']
            candidate_hostid=host['id']
            net_out.write(
                'Found candidate host for migration'
                'id = %s : name = %s \n' %
                (candidate_hostid, candidate_hostname)
            )
            break

    if candidate_hostid=='Null':
        net_out.write(
                'Did not find candidate host for migration %s'
                ' vmid = %s \n' %
                (vm_name,vm_id)
            )
        return False

    ### Try to migrate the vm to the actually selected  host ###
    request = {
        'virtualmachineid': vm_id,
        'hostid': candidate_hostid,
    }   

    result = api.migrateVirtualMachine(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed job to migrate virtualmachine  %s'
            ' Response was %s\n' %
            (vm_name, result),
        )
        return False

    result = wait_for_job(result['jobid'], api)

    if result == {} or 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Failed to migrate volume  %s.'
            ' Response was %s\n' % (vm_id, result),
        )
        return False

    result_vm=result['virtualmachine']
    if result_vm['hostid']==candidate_hostid:
        net_out.write(
            'vm %s migrated successfully to host %s \n' %
            (vm_name, candidate_hostname),
        )
        return result_vm
    else:
        net_out.write(
            'ERROR: vm %s migration to host %s failed \n' %
            (vm_name, candidate_hostname),
        )
        return result_vm

def delete_network(network_id,api,net_out):
    net_out.write('--------- DELETE NETWORK---------\n')
    net_out.write('Network ID: %s\n' % network_id)

    request = {
        'id': network_id,
        'listall': 'True'
    }
    network_result=api.listNetworks(request)
    if network_result == {} or 'network' not in network_result:
        net_out.write(
            'ERROR: Failed to find network to be deleted  %s. '
            ' Response was %s\n' %
            (network_id, network_result),
        )
        return False

    network_name=network_result['network'][0]['name']
    net_out.write('Network Name: %s\n' % network_name)
    
    request = {
        'id': network_id,
    }
    result = api.deleteNetwork(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed to create job to netelet network  %s. '
            ' Response was %s\n' %
            (network_id, result),
        )
        return False

    result = wait_for_job(result['jobid'], api)
    if result=={} or 'success' not in result:
        net_out.write(
            'ERROR:Failed to delete network %s.'
            'Response was %s\n' % (network_id, result),
        )
        return False

    if result['success']:
        net_out.write(
            'Network successfully deleted.\n'
        )
        return True
    else:
        net_out.write(
            'ERROR:Failed to delete network %s.'
            'Response was %s\n' % (network_id, result),
        )
        return False




def delete_vm(vm_id,api,net_out):  
    # --------- DELETION ---------
    net_out.write('--------- DELETION ---------\n')

### We don't shutdown the vm to destroy it 
    # Shutdown
### command = 'shutdown -h now'
    ### ssh_out = ssh_command(command, ip_address, vm_password, public_port)
    ### net_out.write('Shutting down VM...\n')

    ### # Wait for shutdown to start
    ### time.sleep(60)

    ### # Check Shutdown
    ### command = 'echo hello'
    ### ssh_out = ssh_command(command, ip_address, vm_password, public_port)
    ### if ssh_out is '':
        ### net_out.write('VM successfully shut down.\n')
    ### else:
        ### net_out.write('VM did not shutdown correctly.\n')
        ### return False

    # Destroy VM
    request = {
        'id': vm_id,
    }
    destroy_result = api.destroyVirtualMachine(request)
    net_out.write('Deleting VM...\n')

    destroy_result = wait_for_job(destroy_result['jobid'], api)

    # Check VM deletion succeeded
    counter = 0
    timeout = 30
    while counter < timeout:
        counter += 1

        request = {
            'id': vm_id,
        }
        result = api.listVirtualMachines(request)

        if result == {}:
            net_out.write('The VM has been already expunged.\n')
            break

        elif 'virtualmachine' in result:

            if len(result['virtualmachine']) != 1:
                net_out.write(
                    'ERROR: Unexpected result deleting virtual machine: %s '
                    'Virtual machine destroy result was: %s\n' %
                    (result, destroy_result),
                )
                return False

            elif result['virtualmachine'][0]['state'] == 'Destroyed':
                net_out.write(
                    'The VM has been deleted successfully.\n'
                )
                break

            elif counter == timeout:
                net_out.write(
                    'ERROR: TimeOut. The VM has not been deleted. %s '
                    'Virtual machine destroy result was: %s\n' %
                    (result, destroy_result),
                )
                return False
        else:
            net_out.write(
                'ERROR: The deletion check failed %s\n'
                'Virtual machine destroy result was: %s\n' %
                (result, destroy_result)
            )
            return False
        time.sleep(60)

    # Expunge VM
    request = {
        'id': vm_id,
        'expunge': 'True',
    }

    expunge_result = api.destroyVirtualMachine(request)
    net_out.write('Expunging VM...\n')

    expunge_result = wait_for_job(expunge_result['jobid'], api)

    # Check VM expunging succeeded
    counter = 0
    timeout = 30
    while counter < timeout:
        counter += 1

        request = {
            'id': vm_id,
        }
        result = api.listVirtualMachines(request)

        if result == {}:
            net_out.write('The VM has been successfully expunged.\n')
            break

        elif counter == timeout:
            net_out.write(
                'ERROR: TimeOut. The VM has not been expunged. %s '
                'Virtual machine expunging result was: %s\n' %
                (result, expunge_result),
            )
            return False

    # Everything has been successfull (if we get here)
    net_out.write('--------- END DELETION ---------\n')
    return True

def create_network(zone_id, domain_id, account_name, network_name, api, net_out, gateway='192.168.0.1'):

    # Assuming the network offering is PrivateWithGatewayServices
    request = {
        'name': 'PrivateWithGatewayServices'
    }
    networkoffering_result=api.listNetworkOfferings(request)
    if  networkoffering_result == {} or networkoffering_result['count'] == 0:
        print( 'No network offering PrivateWithGatewayServices found' )
    networkoffering_id=networkoffering_result['networkoffering'][0]['id']
    ##output( 'Networkofferingid is %s' % networkoffering_id)

    ### Check if a network with same network name and offering id already exists

    request = {
        'name': network_name,
        'networkofferingid': networkoffering_id,
        'domainid': domain_id,
        'zone_id': zone_id,
        'listall': 'True'
    }

    network_result=api.listNetworks(request)
    if 'network' in network_result:
        for network in network_result['network']:
            if network['name']==network_name:
                network_id=network['id']
                output(
                    'Network %s already exists. ID is %s\n'  %
                    (network_name, network_id)
                )
                return network_id

    #Actually  Deploy the network if not found
    request = {
        'displaytext': network_name,
        'name': network_name,
        'networkofferingid': networkoffering_id,
        'zoneid': zone_id,
        'account': account_name,
        'domainid': domain_id,
        'gateway': gateway,
        'netmask': '255.255.255.0',
    }

    network_result=api.createNetwork(request)

    if network_result == {} or 'network' not in network_result.keys():
        output(
            'ERROR: Failed to deploy  network %s. '
            ' Response was %s\n' %
            (network_name, network_result),
        )
        return False

    output('Deploying network %s.\n' % network_name)

    network_id = network_result['network']['id']
    output(
        'network %s successfully deployed for domain %s.\n'
        % (network_name, domain_id),
    )

    return network_id



def get_usercontext(user_name,admin_api):
    
    #Check if the api_key exists, otherwise request them
    request = {
        'username': user_name
    }
    result = admin_api.listUsers(request)
    if result == {} or 'user' not in result.keys():
        output(
            'ERROR: Failed get data for user %s'
            ' Response was %s\n' %
            (user_name, result),
        )
        return False
    user=result['user'][0]
    if 'apikey' in user:
        print('Found keys for user %s' % user_name)
        user_api_key=user['apikey'] 
        user_api_secret=user['secretkey'] 
        output('apikey %s:' % user_api_key)
    else:
        output('Keys for user %s not found' % user_name)
        output('Generating new keys')
        request = {
            'id': user['id']
        }
        result=admin_api.registerUserKeys(request)
        if result == {} or 'userkeys' not in result:
            output(
                'ERROR: Failed to create new keys for user %s'
                ' Response was %s\n' %
                (user_name, result),
            )
            return False
        userkeys=result['userkeys']
        user_api_key=userkeys['apikey']
        user_api_secret=userkeys['secretkey']

    ### Return the user context as dictionary ###
    ### We get the api_url from the user context
    api_url=admin_api.context['api_url']
    return {
        'api_key': user_api_key,
        'api_secret': user_api_secret,
        'api_url': api_url
    }

def create_vmsnapshot(vm_id,api,net_out):
    net_out.write('Creating snapshot of vm %s ...\n' % vm_id)
    request = {
        'virtualmachineid': vm_id,
    }
    result = api.createVMSnapshot(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed to create job to take snapshot of VM %s. '
            ' Response was %s\n' %
            (vm_id, result),
        )
        return False

    result = wait_for_job(result['jobid'], api)
    if result == {} or 'vmsnapshot' not in result:
        net_out.write(
            'ERROR: Failed to take snapshot of VM %s.'
            ' Response was %s\n' % (vm_id, result),
        )
        return False
    if result['vmsnapshot']['virtualmachineid'] != vm_id:
        net_out.write(
            'ERROR: Failed to take snapshot of VM %s.'
            ' Response was %s\n' % (vm_id, result),
        )
        return False

    # Define snapshot ID
    vm_snapshot_id = result['vmsnapshot']['id']

    net_out.write(
        'Snapshot %s of VM %s successfully taken.\n'
        % (vm_snapshot_id, vm_id),
    )
    return vm_snapshot_id


def delete_vmsnapshot(vm_id,vm_snapshot_id,api,net_out):
    net_out.write('Deleting snapshot %s of vm %s ...\n' % (vm_snapshot_id,vm_id))
    request= {
        'vmid': vm_id,
        'vmsnapshotid': vm_snapshot_id,
        'listall': 'True',
    }
    result=api.listVMSnapshot(request)
    if result == {} or 'vmSnapshot' not in result:
        net_out.write(
            'ERROR: Failed to find snapshot %s of VM %s.'
            ' Response was %s\n' % (vm_snapshot_id,vm_id, result),
        )
        return False
    ### We try to delete vm snapshot ###
    request= {
        'vmsnapshotid': vm_snapshot_id,
    }
    result=api.deleteVMSnapshot(request)
    if result == {} or 'jobid' not in result:
        net_out.write(
            'ERROR: Failed to delete snapshot %s of VM %s.'
            ' Response was %s\n' % (vm_snapshot_id,vm_id, result),
        )
        return False
    
    result = wait_for_job(result['jobid'], api)

    if result == {} or 'success' not in result:
        net_out.write(
            'ERROR: Failed to delete snapshot %s of VM %s.'
            ' Response was %s\n' % (vm_snapshot_id,vm_id, result),
        )
    else:
        if result['success']:
            net_out.write(
                'Successfully deleted snapshot %s of VM %s.'
                % (vm_snapshot_id,vm_id),
            ) 
            return True
        
def upload_template(template_name,zone_id,domain_id,account_name,api,net_out):
    net_out.write('Uploading template %s ...\n' % (template_name))

    request={}

    result=api.listOsTypes(request)
    ostype_list=result['ostype']
    ostype_ids={}
    for ostype in ostype_list:
        if ostype['description']=='Debian GNU/Linux 7(64-bit)':
            ostype_ids['Debian']=ostype['id']
        elif ostype['description']=='CentOS 6.4 (64-bit)':
            ostype_ids['CentOS']=ostype['id']

    ### We Hardcode Centos64.ova template
    request={
        'displaytext': template_name,
        'format': 'OVA',
        'hypervisor': 'VMWare',
        'name': template_name,
        'ostypeid': ostype_ids['CentOS'],
        'url': 'http://10.220.2.77/centos64.ova',
        'zoneid': zone_id,
        'isfeatured': 'True',
        'ispublic': 'True',
        'domainid': domain_id,
        'account': account_name,
        'passwordenabled': True,
        'isdynamicallyscalable': True,
    } 

    result = api.registerTemplate(request)

    if result == {} or 'template' not in result:
        net_out.write(
            'ERROR: Failed job to register template %s. '
            ' Response was %s\n' %
            (template_name, result),
        )
        return False

    template_id = result['template']['id']
    net_out.write(
        'Template successfully registered on zone %s with ID %s.\n'
        % (template_id, zone_id)
    )

    net_out.write('Waiting for template in ready state')
    current_time = 0
    timeout = 60
    while current_time < timeout:
        request = {
            'id': template_id,
            'templatefilter': 'self',
        }
        result = api.listTemplates(request)
        if result['template'][0]['isready'] == 'True':
            net_out.write('Template in %s state' % result['template'][0]['state'])
            return template_id
        current_time += 2
        time.sleep(2)
    return False


def upload_iso(iso_name,bootable,zone_id,domain_id,account_name,api,net_out):
    net_out.write('Uploading ISO %s ...\n' % (iso_name))

    request={}

    result=api.listOsTypes(request)
    ostype_list=result['ostype']
    ostype_ids={}
    for ostype in ostype_list:
        if ostype['description']=='Debian GNU/Linux 7(64-bit)':
            ostype_ids['Debian']=ostype['id']
        elif ostype['description']=='CentOS 6.4 (64-bit)':
            ostype_ids['CentOS']=ostype['id']

    ### We Hardcode Centos65.ISO template
    request={
        'displaytext': iso_name,
        'format': 'OVA',
        'hypervisor': 'VMWare',
        'name': iso_name,
        'ostypeid': ostype_ids['CentOS'],
        'url': 'http://10.220.2.77/CentOS-6.5-x86_64-minimal.iso',
        'zoneid': zone_id,
        'isfeatured': 'True',
        'ispublic': 'False',
        'domainid': domain_id,
        'account': account_name,
        'bootable': bootable,
    }

    result = api.registerIso(request)

    if result == {} or 'iso' not in result:
        net_out.write(
            'ERROR: Failed job to register ISO %s. '
            ' Response was %s\n' %
            (iso_name, result),
        )
        return False

    iso_id = result['iso'][0]['id']
    net_out.write(
        'ISO successfully registered on zone %s with ID %s.\n'
        % (iso_id, zone_id)
    )

    net_out.write('Waiting for ISO in ready state')
    current_time = 0
    timeout = 60
    while current_time < timeout:
        request = {
            'id': iso_id,
            'isofilter': 'self',
        }
        result = api.listIsos(request)
        print(result['iso'][0]['isready'])
        if result['iso'][0]['isready']:
            net_out.write(
                'ISO %s with ID %s ready: %s\n' %
                (iso_name,iso_id,result['iso'][0]['isready'])
            )
            return iso_id
        current_time += 2
        time.sleep(10)
    return False

################## BASIC TEST ##############################
            
def basic_test(
    zone_id, 
    network_name, 
    template_id, 
    domain_id,
    account_name, 
    api,):

    # Create output file
    net_out = open('out_%s' % network_name, 'w')
    net_out.write(
        'vm_test for network %s at %s\n' %
        (network_name, datetime.datetime.now())
    )
    net_out.write('-----------------------------------------------------\n\n')

    # --------- CREATION ---------
    net_out.write('--------- CREATION ---------\n')

    # Create the network
    network_id=create_network(zone_id, domain_id, account_name, network_name, api, net_out)
    print(network_id)
    if network_id == False:
        net_out.write(
            'ERROR: Failed to create network %s' %
            network_name
        )
    net_out.write(
        'Create network %s with ID %s\n' %
        (network_name,network_id)
    )

    # Deploy VM
    vm_name='%s-vm1' % network_name

    #print('Before Deploy VM template ID %s\n' % template_id)
    vm_id=deploy_vm(
        vm_name=vm_name,
        zone_id=zone_id,
        network_id=network_id,
        domain_id=domain_id,
        account_name=account_name,
        net_out=net_out,
        api=api,
        template_id=template_id,
        offering_name='Medium Instance',
        startvm='False',
    )
    if vm_id == False:
        return False

#### From this point if there is an error destroy the vm and the network

    # Start VM
    vm_password=start_vm(vm_id,api,net_out)
    if vm_password == False:
    ### Adding clean up stuff
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    # Reboot VM #
    request = {'id': vm_id}
    result = api.rebootVirtualMachine(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed to create job to reboot VM on network %s. '
            ' Response was %s\n' % (network_id, result),
        )
    ### Adding clean up stuff
        delete_vm(vm_id,api,net_out)
        return False
    net_out.write('Rebooting VM...\n')

    result = wait_for_job(result['jobid'], api)

    if result == {} or 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Failed to reboot VM on network %s.'
            ' Response was %s\n' % (network_id, result),
        )
    ### Adding clean up stuff
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    # Stop VM
    stop_success = stop_vm(vm_id,api,net_out)
    if stop_success == False:
    ### Adding clean up stuff
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False


    ### Reset the password ### 
    net_out.write('Resetting passwort of VM...\n')

    vm_password=reset_password(vm_id,api,net_out)
    if vm_password == False:
        net_out.write(
            'ERROR: Failed to reset password' 
        )
    ### Adding clean up stuff
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False
    else:
         net_out.write(
            'new password: %s\n' % vm_password 
        )


    ### Skipping vm rebuild for now ###
    ##new_vm_id=rebuild_vm(vm_id,api,net_out)
    ##if new_vm_id == False:
        ##net_out.write(
            ##'ERROR: Failed to rebuild vm\n' 
        ##)
    ### Adding clean up stuff
        ##delete_vm(vm_id,net_out)
        ##delete_network(network_id,net_out)
        ##return False
    ##else:
         ##net_out.write(
            ##'new vm id: %s\n' % new_vm_id
        ##)

    ### Creating a volume and attaching it to the VM
    net_out.write( 'Creating an additional volume:\n' )
    volume_name = ('%s-vol1' % network_name)
    disk_offering_name='EBS'
    volume_size='10'
    time.sleep(60)
    volume_id=create_volume(volume_name,volume_size,disk_offering_name,zone_id,account_name,domain_id,api,net_out)
    if volume_id == False:
	### Adding clean up stuff
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    net_out.write(
        'Volume %s successfully created on zone %s.\n'
        % (volume_id, zone_id)
    )

    # Attach volumes
    result_attach=attach_volume(volume_id,vm_id,api,net_out)
    if result_attach == False:
    ### Adding clean up stuff
        delete_volume(volume_id,vm_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    #### At this point we call the function to remove the volume
    delete_volume(volume_id,vm_id,api,net_out)
    ### No error control, just calling the function
### No need to delete the volume beyond this point 

    # Start VM again
    start_success=start_vm(vm_id,api,net_out)
    if start_success == False:
	### Adding clean up stuff
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    # Take VM snapshot
    vm_snapshot_id=create_vmsnapshot(vm_id,api,net_out)
    if vm_snapshot_id == False:
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    # Delete VM snapshot
    delete_snapshot_success=delete_vmsnapshot(vm_id,vm_snapshot_id,api,net_out)
    print('delete_snapshot_success %s\n' % delete_snapshot_success)
    if delete_snapshot_success == False:
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    ### Stop the VM again
    stop_success = stop_vm(vm_id,api,net_out)
    if stop_success == False:
    ### Adding clean up stuff
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False
    
    ### Change compute offering to Tiny
    scale_result=scale_vm(vm_id,'Tiny Instance',api,net_out)
    if scale_result == False:
        net_out.write(
            'ERROR: Problem resizing VM'
        )
    ### Adding clean up stuff
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    # Start VM again
    start_success=start_vm(vm_id,api,net_out)
    if start_success == False:
    ### Adding clean up stuff
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    ### Change compute offering to Huge
    scale_result=scale_vm(vm_id,'Huge Instance',api,net_out)
    ### DEBUG ###
    return True
    ### DEBUG ###
    if scale_result == False:
        net_out.write(
            'ERROR: Problem resizing VM'
        )
    ### Adding clean up stuff
        ##delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    ### Finish testing
    net_out.write('-------------Finished testing. Cleaning UP ...-------------\n')
    delete_vm(vm_id,api,net_out)
    delete_network(network_id,api,net_out)
    return True

##################### STORAGE TEST #####################################

def storage_test(
    zone_id, 
    network_name, 
    template_id, 
    domain_id,
    account_name, 
    ostype_id,
    api,):

    # Create output file
    net_out = open('out_%s' % network_name, 'w')
    net_out.write(
        'vm_test for network %s at %s\n' %
        (network_name, datetime.datetime.now())
    )
    net_out.write('-----------------------------------------------------\n\n')

    # --------- CREATION ---------
    net_out.write('--------- CREATION ---------\n')

    # Create the network
    network_id=create_network(zone_id, domain_id, account_name, network_name, api, net_out)
    ##print(network_id)
    if network_id == False:
        net_out.write(
            'ERROR: Failed to create network %s' %
            network_name
        )
    net_out.write(
        'Create network %s with ID %s\n' %
        (network_name,network_id)
    )

    ### Define vm_names
    vm_name='%s-vm1' % network_name
    volume_name1='%s-vol1' % network_name
    volume_name2='%s-vol2' % network_name
    volume_name3='%s-vol3' % network_name

    # Deploy VM
    vm_id=deploy_vm(
        vm_name=vm_name,
        zone_id=zone_id,
        network_id=network_id,
        domain_id=domain_id,
        account_name=account_name,
        net_out=net_out,
        api=api,
        template_id=template_id,
        offering_name='Medium Instance',
        startvm='False',
    )
    if vm_id == False:
        return False

#### From this point if there is an error destroy the vm and the network

    # Start VM
    vm_password=start_vm(vm_id,api,net_out)
    if vm_password == False:
    ### Adding clean up stuff
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

### We add portforwarding rules to be able to SSH to the VM directly ###

    port_forwarding_data=add_portforwarding(network_id,vm_id,api,net_out)

    ip_address=port_forwarding_data['IP']
    public_port=port_forwarding_data['public_port']
    portforward_id=port_forwarding_data['portforward_id']
    
    # Suppress error messages from paramiko
    logging.getLogger('paramiko').addHandler(logging.NullHandler())


    ### Create a data volume1
    disk_offering_name='EBS'
    volume_size='10'
    volume_id1=create_volume(volume_name1,volume_size,disk_offering_name,zone_id,account_name,domain_id,api,net_out)
    if volume_id1 == False:
    ### Adding clean up stuff
        remove_portforwarding(portforward_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False
    
    ### Attach Volume1
    result_attach=attach_volume(volume_id1,vm_id,api,net_out)
    if result_attach == False:
    ### Adding clean up stuff
        remove_portforwarding(portforward_id,api,net_out)
        delete_volume(volume_id1,vm_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    ### Resize Volume1
    volume_size='15'
    result_resize=resize_volume(volume_id1,volume_size,api,net_out)
    if result_resize == False:
    ### Adding clean up stuff
        remove_portforwarding(portforward_id,api,net_out)
        delete_volume(volume_id1,vm_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    ### Connect to the VM and create a file ###
    net_out.write('Trying to format the new disk\n') 
    
    # Rescan SCSI bus for discovering new attached volumes
    command = (
        'for controller in /sys/class/scsi_host/*; '
        'do echo "- - -"> $controller/scan; done'
    )
    ssh_command(command, ip_address, vm_password, public_port)
    # Format attached volumes
    command = (
        'pvcreate /dev/sdb; ' 
        'vgcreate datavg /dev/sdb; ' 
        'lvcreate -l 100%FREE -n datavol datavg; ' 
        'mkfs -t ext4 /dev/datavg/datavol'
    )
    ssh_out=ssh_command(command, ip_address, vm_password, public_port)
    net_out.write(ssh_out)
    # Mount attached volumes
    command = (
        'mkdir /media/volume_test; '
        'mount /dev/datavg/datavol /media/volume_test; '
        'touch /media/volume_test/testfile; '
    )
    ssh_out=ssh_command(command, ip_address, vm_password, public_port)
    net_out.write(ssh_out)
    # Check if Volumes are mounted
    command = 'mount'
    ssh_out = ssh_command(command, ip_address, vm_password, public_port)
    net_out.write(ssh_out)
    if 'datavol' in ssh_out:
        net_out.write(
            'Volume formatted and mounted.\n'
        )
    else:
        net_out.write(
            'ERROR: Volume not formatted or mounted properly.\n %s \n' % ssh_out
        )
        remove_portforwarding(portforward_id,api,net_out)
        delete_volume(volume_id1,vm_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    # Add a testfile and umount the disk
    command = (
        'touch /media/volume_test/test_file; '
        'umount /media/volume_test; '
        'vgexport datavg; '
    )
    ssh_out=ssh_command(command, ip_address, vm_password, public_port)
    net_out.write(ssh_out)

    
    ### Snapshot Data Volume1
    snapshot_id1=snapshot_volume(volume_id1,api,net_out)
    if snapshot_id1 == False:
    ### Adding clean up stuff
        remove_portforwarding(portforward_id,api,net_out)
        delete_volume(volume_id1,vm_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    ### Create Volume from snapshot
    volume_id2=create_volume_fromsnap(volume_name2,snapshot_id1,zone_id,api,net_out)
    if volume_id2 == False:
    ### Adding clean up stuff
        remove_portforwarding(portforward_id,api,net_out)
        delete_volume(volume_id1,vm_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    ### Delete volume1 ###
    result_delete=delete_volume(volume_id1,vm_id,api,net_out)
    if result_delete == False:
    ### Adding clean up stuff
        remove_portforwarding(portforward_id,api,net_out)
        delete_volume(volume_id2,vm_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    result_attach=attach_volume(volume_id2,vm_id,api,net_out)
    if result_attach == False:
    ### Adding clean up stuff
        remove_portforwarding(portforward_id,api,net_out)
        delete_volume(volume_id2,vm_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    # Rescan SCSI bus for discovering new attached volumes
    command = (
        'for controller in /sys/class/scsi_host/*; '
        'do echo "- - -"> $controller/scan; done'
    )
    ssh_out=ssh_command(command, ip_address, vm_password, public_port)
    net_out.write(ssh_out)

    ### Try to reimport the volume group    
    command = (
        'pvscan; '
        'vgimport datavg; '
        'vgchange -ay datavg; '
        'lvchange -ay datavg/datavol; '
        'mount /dev/datavg/datavol /media/volume_test; '
    )
    ssh_out = ssh_command(command, ip_address, vm_password, public_port)
    net_out.write(ssh_out)
    ### Check if the file is there
    command = 'find /media/volume_test/test_file'
    ssh_out = ssh_command(command, ip_address, vm_password, public_port)
    net_out.write(ssh_out)

    if 'test_file' in ssh_out:
        net_out.write(
            "Volume's data appears to be OK.\n"
        )
    else:
        net_out.write(
            "ERROR: Volume's data corrupted.\n"
        )
         ### Adding clean up stuff
        remove_portforwarding(portforward_id,api,net_out)
        delete_volume(volume_id2,vm_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    ### Delete Volume2
    result_delete=delete_volume(volume_id2,vm_id,api,net_out)
    if result_delete == False:
    ### Adding clean up stuff
        remove_portforwarding(portforward_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    ### Upload a volume3 
    ### Define Test Volume URL
    disk_offering_name='EBS'
    volume_url='http://10.220.2.77/uploadvol.ova'
    volume_id3=upload_volume(volume_name3,volume_url,disk_offering_name,zone_id,account_name,domain_id,api,net_out)
    if volume_id3 == False:
    ### Adding clean up stuff
        remove_portforwarding(portforward_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    ### Attach Volume3
    result_attach=attach_volume(volume_id3,vm_id,api,net_out)
    if result_attach == False:
    ### Adding clean up stuff
        remove_portforwarding(portforward_id,api,net_out)
        delete_volume(volume_id3,vm_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    ### Verify we can access the data in the disk ###
    command = (
        'for controller in /sys/class/scsi_host/*; '
        'do echo "- - -"> $controller/scan; done '
    )
    ssh_command(command, ip_address, vm_password, public_port)
    
    command = (
        'pvscan; '
        'vgimport uploadvg; '
        'vgchange -ay uploadvg; '
        'lvchange -ay uploadvg/uploadvol; '
        'mkdir /mnt/upload; '
        'mount /dev/uploadvg/uploadvol /mnt/upload; '
        'ls /mnt/upload/*txt '
    )
    ssh_out = ssh_command(command, ip_address, vm_password, public_port)

    test = ('upload.txt' not in ssh_out.lower())
    if test:
        net_out.write(
            'Could not find upload.txt file'
        )
        remove_portforwarding(portforward_id,api,net_out)
        delete_volume(volume_id3,vm_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False
    else:
        net_out.write(
            'upload.txt file found. uploadvol successfully mounted.\n'
            'Prompted: %s\n'
            % ssh_out,
        )

    command = (
        'umount /mnt/upload; '
        'vgexport uploadvg '
    )
    ssh_out = ssh_command(command, ip_address, vm_password, public_port)

    ### Delete Volume3
    delete_volume(volume_id3,vm_id,api,net_out)
    ### We don't error control this

    ### Snapshot root volume
    rootvol_snapshot_id=snapshot_rootvol(vm_id,api,net_out)
    if rootvol_snapshot_id == False:
    ### Adding clean up stuff
        remove_portforwarding(portforward_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    ### Create Template from snapshot
    rootvol_template_id1=create_template_fromsnap(rootvol_snapshot_id,ostype_id,domain_id,account_name,api,net_out)
    if rootvol_template_id1 == False:
    ### Adding clean up stuff
        remove_portforwarding(portforward_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False
    net_out.write('rootvol_template_id1 is %s\n' % rootvol_template_id1)
    
    ### Deploy a VM from this template
    rootvol_vm_name1='rootvm1-'+vm_name
    rootvol_vm_id1=deploy_vm(
        vm_name=rootvol_vm_name1,
        zone_id=zone_id,
        network_id=network_id,
        domain_id=domain_id,
        account_name=account_name,
        net_out=net_out,
        api=api,
        template_id=rootvol_template_id1,
        offering_name='Medium Instance',
        startvm='False',
    )
    if rootvol_vm_id1 == False:
        remove_portforwarding(portforward_id,api,net_out)
        delete_template(rootvol_template_id1,api,net_out)
        delete_snapshot(rootvol_snapshot_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    # Start VM
    rootvol_vm_password1=start_vm(rootvol_vm_id1,api,net_out)
    if rootvol_vm_password1 == False:
        delete_vm(rootvol_vm_id1,api,net_out)
        remove_portforwarding(portforward_id,api,net_out)
        delete_template(rootvol_template_id1,api,net_out)
        delete_snapshot(rootvol_snapshot_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    ### Delete the VM from the tests
    delete_vm(rootvol_vm_id1,api,net_out) 
    delete_template(rootvol_template_id1,api,net_out)
    delete_snapshot(rootvol_snapshot_id,api,net_out)
    ### We don't error control the deletion of this components ###

    ### Stop the main VM 
    stop_success = stop_vm(vm_id,api,net_out)
    if stop_success == False:
    ### Adding clean up stuff
        remove_portforwarding(portforward_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    ### Create template from rootvol directly ###
    ### Create Template from snapshot
    rootvol_template_id2=create_template_fromrootvol(vm_id,ostype_id,domain_id,account_name,api,net_out)
    if rootvol_template_id2 == False:
    ### Adding clean up stuff
        remove_portforwarding(portforward_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False
    net_out.write('rootvol_template_id2 is %s\n' % rootvol_template_id2)

    ### Deploy a VM from this template
    rootvol_vm_name2='rootvm2-'+vm_name
    rootvol_vm_id2=deploy_vm(
        vm_name=rootvol_vm_name2,
        zone_id=zone_id,
        network_id=network_id,
        domain_id=domain_id,
        account_name=account_name,
        net_out=net_out,
        api=api,
        template_id=rootvol_template_id2,
        offering_name='Medium Instance',
        startvm='False',
    )
    if rootvol_vm_id2 == False:
        remove_portforwarding(portforward_id,api,net_out)
        delete_template(rootvol_template_id2,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    # Start VM
    rootvol_vm_password2=start_vm(rootvol_vm_id2,api,net_out)
    if rootvol_vm_password2 == False:
        delete_vm(rootvol_vm_id2,api,net_out)
        remove_portforwarding(portforward_id,api,net_out)
        delete_template(rootvol_template_id2,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    ### Delete the VM from the tests
    delete_vm(rootvol_vm_id2,api,net_out)
    delete_template(rootvol_template_id2,api,net_out)

    ### Create some snapshot schedules
    ### Create hourly snapshot schedule
    schedule='HOURLY'
    hourly_snapshotpolicy_id=create_snapshot_schedule(volume_id1,schedule,api,net_out)
    if hourly_snapshotpolicy_id == False:
        remove_portforwarding(portforward_id,api,net_out)
        delete_volume(volume_id1,vm_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
    else:
         net_out.write('Hourly snapshot policy' % hourly_snapshotpolicy_id)           

    ### Create daily snapshot schedule
    schedule='DAILY'
    daily_snapshotpolicy_id=create_snapshot_schedule(volume_id1,schedule,api,net_out)
    if daily_snapshotpolicy_id == False:
        remove_portforwarding(portforward_id,api,net_out)
        delete_volume(volume_id1,vm_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
    else:
        net_out.write('Daily snapshot policy %s\n' % daily_snapshotpolicy_id)

    ### Finish testing
    net_out.write('-------------Finished testing. Cleaning UP ...-------------\n')
    net_out.write('-------------Finished testing. Network1,VM and volume1 stay behind -------------\n')
    remove_portforwarding(portforward_id,api,net_out)
    return True

################### VALIDATE SNAPSHOT POLICY ###########

def validate_snashot_policy(
    zone_id,
    template_id,
    domain_id,
    account_name,
    vm_id,
    api,):

    ### Get the data of the virtual machine ### 
    request = {
            'id': vm_id,
        }
    result = api.listVirtualMachines(request)
    if result == {} or 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Could not find vm with id %s\n'
            'Result was %s\n' %
            (vm_id, result)
        )
    vm=result['virtualmachine'][0]
    vm_name=vm['name']

    ### Get the actual rootvol  ### 
    request = {
        'virtualmachineid': vm_id,
        'listall': 'True',
        'type':  'ROOT',
    }

    result = api.listVolumes(request)
    if result == {} or 'volume' not in result:
        net_out.write(
            'ERROR: Failed to find ROOT volume for vm %s.'
            ' Response was %s\n' % (vm['name'], result)
        )
        return False
    volume=result['volume']
    volume_id=volume[0]['id']
    volume_name=volume[0]['name']

    ### Check the snashotpolicy ###
    request={
        'vollumeid': volume_id
    }
    result=api.listSnapshotPolicies(request)
    if result == {} or 'snapshotpolicy' not in result:
        net_out.write(
            'ERROR: Root volume does not have snapshot policies\n'
        )
    snapshot_policies=result['snapshotpolicy']

    for policy in snapshot_policies:
        pprint(policy) 

    return True
    
##################### NETWORK TEST #####################################

def network_test(
        zone_id,
        network_name,
        template_id,
        domain_id,
        account_name,
        ostype_id,
        api,):

    # Create output file
    net_out = open('out_%s' % network_name, 'w')
    net_out.write(
        'vm_test for network %s at %s\n' %
        (network_name, datetime.datetime.now())
    )
    net_out.write('-----------------------------------------------------\n\n')

    # --------- CREATION ---------
    net_out.write('--------- CREATION ---------\n')

    # Create the network
    network_id=create_network(zone_id, domain_id, account_name, network_name, api, net_out)
    ##print(network_id)
    if network_id == False:
        net_out.write(
            'ERROR: Failed to create network %s' %
            network_name
        )
    net_out.write(
        'Create network %s with ID %s\n' %
        (network_name,network_id)
    )

    ### Define vm_names
    vm_name='%s-vm1' % network_name

    # Deploy VM
    vm_id=deploy_vm(
        vm_name=vm_name,
        zone_id=zone_id,
        network_id=network_id,
        domain_id=domain_id,
        account_name=account_name,
        net_out=net_out,
        api=api,
        template_id=template_id,
        ip_address='192.168.0.2',
        offering_name='Medium Instance',
        startvm='False',
    )
    if vm_id == False:
        return False

    # Start VM
    vm_password=start_vm(vm_id,api,net_out)
    if vm_password == False:
    ### Adding clean up stuff
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False
    
    ### We add portforwarding rules to be able to SSH to the VM directly ###

    port_forwarding_data=add_portforwarding(network_id,vm_id,api,net_out)
    if  port_forwarding_data == False:
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
        
    ip_address=port_forwarding_data['IP']
    public_port=port_forwarding_data['public_port']
    portforward_id=port_forwarding_data['portforward_id']

    # Suppress error messages from paramiko
    logging.getLogger('paramiko').addHandler(logging.NullHandler())

    ### We create the fw egress rules for port 80 and 53

    egress_ids=create_egress(network_id,api,net_out)
    if egress_ids == False:
        remove_portforwarding(portforward_id,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)

    ### Acquire a public IP
    ipaddress_id=get_public_ip(network_id,api,net_out) 
    if ipaddress_id == False:
        remove_portforwarding(portforward_id,api,net_out)
        remove_egress(egress_ids,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)

    ### Create a Static NAT from the public IP to the selected VM
    nat_success=enable_nat(ipaddress_id,vm_id,network_id,api,net_out)
    if nat_success==False:
        release_public_ip(ipaddress_id,network_id,api,net_out) 
        remove_portforwarding(portforward_id,api,net_out)
        remove_egress(egress_ids,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)

    ### Add firewall rules ###

    ### fwrule_id=add_firewall_rule(ipaddress_id,network_id,protocol,cidr_list,start_port,end_port,api,net_out)
    fwrule_id=add_firewall_rule(ipaddress_id,network_id,'TCP','0.0.0.0/0','22000','22000',api,net_out)
    if fwrule_id == False:
        disable_nat(ipaddress_id,api,net_out)
        release_public_ip(ipaddress_id,network_id,api,net_out)
        remove_portforwarding(portforward_id,api,net_out)
        remove_egress(egress_ids,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)

    ### Remove Firewall rule
    success_delete_fwrule=delete_firewall_rule(fwrule_id,api,net_out)
    if success_delete_fwrule == False:
        disable_nat(ipaddress_id,api,net_out)
        release_public_ip(ipaddress_id,network_id,api,net_out)
        remove_portforwarding(portforward_id,api,net_out)
        remove_egress(egress_ids,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)
    
    ### Disable NAT
    success_disable_nat=disable_nat(ipaddress_id,api,net_out)
    if success_disable_nat == False:
        release_public_ip(ipaddress_id,network_id,api,net_out)
        remove_portforwarding(portforward_id,api,net_out)
        remove_egress(egress_ids,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)

    ### Release Public IP
    success_release_ip=release_public_ip(ipaddress_id,network_id,api,net_out)
    if success_disable_nat == False:
        remove_portforwarding(portforward_id,api,net_out)
        remove_egress(egress_ids,api,net_out)
        delete_vm(vm_id,api,net_out)
        delete_network(network_id,api,net_out)

    ### Still need to test second Network ###

    ## Create secondary network
    network_name2=network_name+'-aux' 
    network_id2=create_network(zone_id, domain_id, account_name, network_name2, api, net_out, gateway='192.168.10.1')
    if network_id2 == False:
        net_out.write(
            'ERROR: Failed to create network %s' %
            network_name
        )
    net_out.write(
        'Create network %s with ID %s\n' %
        (network_name,network_id)
    )

    ### Add additional NIC to the VM ###
    
    


    ### Finish testing
    net_out.write('-------------Finished testing. Cleaning UP ...-------------\n')
    remove_portforwarding(portforward_id,api,net_out)
    remove_egress(egress_ids,api,net_out)
    delete_vm(vm_id,api,net_out)
    delete_network(network_id,api,net_out)
    return True


##################### TEMPLATE TEST #####################################

def template_test(
    zone_id,
    network_name,
    template_id,
    domain_id,
    account_name,
    ostype_id,
    api,):

    # Create output file
    net_out = open('out_%s' % network_name, 'w')
    net_out.write(
        'vm_test for network %s at %s\n' %
        (network_name, datetime.datetime.now())
    )
    net_out.write('-----------------------------------------------------\n\n')

    # --------- CREATION ---------
    net_out.write('--------- CREATION ---------\n')

    # Create the network
    network_id=create_network(zone_id, domain_id, account_name, network_name, api, net_out)
    ##print(network_id)
    if network_id == False:
        net_out.write(
            'ERROR: Failed to create network %s' %
            network_name
        )
    net_out.write(
        'Create network %s with ID %s\n' %
        (network_name,network_id)
    )

    ### Define names ###
    vm_name1='%s-vm1' % network_name
    vm_name2='%s-vm2' % network_name
    template_name='%s-template1' % network_name
    iso_name1='%s-iso1' % network_name
    iso_name2='%s-iso2' % network_name

    ### Upload ISO1 ###
    bootable='True'
    iso_id1=upload_iso(iso_name1,bootable,zone_id,domain_id,account_name,api,net_out)
    if iso_id1 == False:
        delete_network(network_id,api,net_out)
        return False

    ### Deploy VM from ISO1 ###
    vm_id2=deploy_vm_iso(
        vm_name2,
        zone_id,
        network_id,
        domain_id,
        account_name,
        net_out,
        iso_id1,
        api,
        disk_offering_name='Small',
        offering_name='Medium Instance',
        startvm='False')

    # Start VM
    vm_start_result=start_vm(vm_id2,api,net_out)
    if vm_start_result == False:
    ### Adding clean up stuff
        delete_vm(vm_id2,api,net_out)
        delete_iso(iso_id1,api,net_out)
        delete_network(network_id,api,net_out)
        return False
    elif  vm_start_result == True:
        output('vm2 started successfully')     

    # Stop VM
    vm_stop_result=stop_vm(vm_id2,api,net_out)
    if vm_stop_result == False:
    ### Adding clean up stuff
        delete_vm(vm_id2,api,net_out)
        delete_iso(iso_id1,api,net_out)
        delete_network(network_id,api,net_out)
        return False
    elif  vm_start_result == True:
        output('vm2 stopped successfully')

    ### We clean_up ###
    delete_vm(vm_id2,api,net_out)
    delete_iso(iso_id1,api,net_out)
    
    ### Upload template1 ###
    template_id=upload_template(template_name,zone_id,domain_id,account_name,api,net_out)
    if template_id1==False:
        delete_network(network_id,api,net_out)
        return False

    ### Deploy the firt vm_id
    vm_id1=deploy_vm(
        vm_name=vm_name1,
        zone_id=zone_id,
        network_id=network_id,
        domain_id=domain_id,
        account_name=account_name,
        net_out=net_out,
        api=api,
        template_id=template_id,
        offering_name='Medium Instance',
        startvm='False',
    )
    if vm_id1 == False:
        delete_template(template_id,api,net_out)
        delete_network(network_id,api,net_out)
        return False 

    # Start VM
    vm_password=start_vm(vm_id1,api,net_out)
    if vm_password == False:
    ### Adding clean up stuff
        delete_vm(vm_id1,api,net_out)
        delete_template(template_id,api,net_out)
        delete_network(network_id,api,net_out)
    
    ### Upload ISO2 ###
    bootable='False'
    iso_id2=upload_iso(iso_name2,bootable,zone_id,domain_id,account_name,api,net_out)
    if iso_id2 == False:
        delete_iso(iso_id2,api,net_out)
        delete_template(template_id,api,net_out)
        delete_vm(vm_id1,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    ### Attach ISO to vm ###
    attach_result=attach_iso(iso_id2,vm_id,api,net_out)
    if attach_result == False:
        delete_iso(iso_id2,api,net_out)
        delete_template(template_id,api,net_out)
        delete_vm(vm_id1,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    ### Prepare Portforwarding Rules ###
    port_forwarding_data=add_portforwarding(network_id,vm_id,api,net_out)

    ip_address=port_forwarding_data['IP']
    public_port=port_forwarding_data['public_port']
    portforward_id=port_forwarding_data['portforward_id']

    # Suppress error messages from paramiko
    logging.getLogger('paramiko').addHandler(logging.NullHandler())


    ### We actually test mounting the ISO
    command = (
        'mkdir /mnt/cdrom; '
        'mount /dev/cdrom1 /mnt/cdrom; '
        'mount; '
    )

    ssh_out = ssh_command(command, ip_address, vm_password, public_port)

    test = ('/mnt/cdrom' not in ssh_out.lower())
    if test:
        net_out.write(
            'Could not find cdrom in mount result'
        )
        remove_portforwarding(portforward_id,api,net_out)
        delete_iso(iso_id2,api,net_out)
        delete_template(template_id,api,net_out)
        delete_vm(vm_id1,api,net_out)
        delete_network(network_id,api,net_out)
        return False
    else:
        net_out.write(
            'cdrom successfully  mounted.\n'
            'Prompted: %s\n'
            % ssh_out,
        )


    ### We umount ISO
    command = (
        'umount /mnt/cdrom'
    )
    ssh_out = ssh_command(command, ip_address, vm_password, public_port)

    ### At this stage we remove the port forwarding ###
    remove_portforwarding(portforward_id,api,net_out)
    ### We don't error control ### 

    result_detach=detach_iso(vm_id,api,net_out)
    if result_detach==False:
        net_out.write(
            'Could not find cdrom in mount result'
        )
        delete_iso(iso_id2,api,net_out)
        delete_template(template_id,api,net_out)
        delete_vm(vm_id1,api,net_out)
        delete_network(network_id,api,net_out)
        return False

    ### Finish testing
    net_out.write('-------------Finished testing. Cleaning UP ...-------------\n')
    remove_portforwarding(portforward_id,api,net_out)
    delete_iso(iso_id2,api,net_out)
    delete_template(template_id,api,net_out)
    delete_vm(vm_id1,api,net_out)
    delete_network(network_id,api,net_out)
    return True
