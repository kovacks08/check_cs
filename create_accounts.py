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
        result= api.queryAsyncJobResult(request)
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

def create_network(zone_id, domain_id, displaytext, network_name, account_id, api):

    # Assuming the network offering is PrivateWithGatewayServices

    request = {
	'name': 'PrivateWithGatewayServices'
    }

    networkoffering_result=api.listNetworkOfferings(request)
    if  networkoffering_result == {} or networkoffering_result['count'] == 0:
        print( 'No network offering PrivateWithGatewayServices found' )
	sys.exit()
    networkoffering_id=networkoffering_result['networkoffering'][0]['id']
    output( 'Networkofferingid is %s' % networkoffering_id)

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
	network_id=network_result['network'][0]['id']
        output(
            'Network already exists %s' 
            ' id is %s\n'  %
            (network_name, network_id),
        )
	return network_id

    #Actually  Deploy the network
    request = {
	'displaytext': displaytext,
	'name': network_name,
	'networkofferingid': networkoffering_id,
	'zoneid': zone_id,
	'account': user_name,
	'domainid': domain_id
	
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
        'network %s successfully deployed for account %s.\n'
        % (network_name, account_id),
	)

    return network_id

def deploy_vm(zone_id, network_id, template_id, api, vm_name, account, domain_id, service_offering_id):
 # Check if VM already exists

    request = { 
        'zoneid': zone_id,
        'networkids': network_id,
        'name': vm_name,
        'displayname': vm_name,
        'account': account,
        'domainid': domain_id
    }

    vm_result = api.listVirtualMachines(request)

    if 'virtualmachine' in vm_result:
	vm_id=vm_result['virtualmachine'][0]['id']
        output(
            'VM already exists %s' 
            ' id is %s\n'  %
            (vm_name, vm_id),
        )
	return vm_id

 # Deploy VM
    request = {
        'serviceofferingid': service_offering_id,
        'templateid': template_id,
        'zoneid': zone_id,
        'networkids': network_id,
        'name': vm_name,
        'displayname': vm_name,
        'startvm': 'True',
	'account': account,
	'domainid': domain_id
    }

    vm_result = api.deployVirtualMachine(request)

    if vm_result == {} or 'jobid' not in vm_result.keys():
        output(
            'ERROR: Failed to create job to deploy VM %s on network %s. '
            ' Response was %s\n' %
            (vm_name, network_id, vm_result),
        )
        return False

    output('Deploying VM on network %s.\n' % network_id)

    vm_result = wait_for_job(vm_result['jobid'], api)

    if vm_result == {} or 'virtualmachine' not in vm_result:
        output(
            'ERROR: Failed to create VM on network %s. Response was %s\n' %
            (network_id, result),
        )
        return False


    vm_id = vm_result['virtualmachine']['id']
    output(
        'VM %s successfully deployed on network %s.\n'
        % (vm_id, network_id),
    )

    return vm_id


def create_domainanduser(user_name,parent_domain_id):

### Check if the domain exists
    request = {
        'id': parentdomain_id,
        'listall': 'True'
    }

    mychildrendomain_result=api.listDomainChildren(request)
    
    mychildrendomain_names = {}
    mychildrendomain_ids = {}

    if mychildrendomain_result == {} or mychildrendomain_result['count'] == 0:
        print( 'No childrendomains for parent_domain %s' % parent_domain )
    else:
        mychildrendomain_ids = [domain['id']
            for domain
            in mychildrendomain_result['domain']]
        mychildrendomain_names = [domain['name']
            for domain
            in mychildrendomain_result['domain']]

    if user_name in mychildrendomain_names:
        output('username %s already exists' % user_name)
        domain_id=mychildrendomain_ids[mychildrendomain_names.index(user_name)]
        output('username associated domain id: %s' % domain_id)
        domain_ids[user_name]=domain_id
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
                return

        user_id=user_result['user'][0]['id']
        user_ids[user_name]=user_id
        account_result = api.listAccounts(request)
        if account_result == {} or account_result['count'] == 0:
                print( 'Username %s not found in existing domain %s\n' %
                (user_name,domain_id)
                )
                return
        account_id=account_result['account'][0]['id']
            
            
            ### Assuming global accoount_ids exist
        account_ids[user_name]=account_id
        return domain_id
    
    request = {
            'name': user_name,
            'parentdomainid': parentdomain_id
        }

    domain_result = api.createDomain(request)
    if domain_result == {}:
        print( "Could not crate domain for user %s" % user_name )
        print(domain_result)
        return
    domain_id = domain_result['domain']['id']
    domain_ids[user_name]=domain_id

    ### Create the account and user
    request = {
            'accounttype': 2,
            'username': user_name,
            'email': 'email@email.com',
            'firstname': base_username,
            'lastname': str(num),
            'password': 'Interoute01',
            'domainid': domain_id
    }

    account_result = api.createAccount(request)
    if account_result == {}:
        print(account_result)
        print( "Could not create user for user %s" % user_name )
        return
    account_id = account_result['account']['id']
    account_user = account_result['account']['user'][0] 
    user_id=account_user['id'] 
    account_ids[user_name]=account_id
    user_ids[user_name]=user_id
       
    return domain_id





def vm_test(zone_id, network_id, template_id, api):
    # Create output file
    net_out = open('out_%s' % network_id, 'w')
    net_out.write(
        'vm_test for network %s at %s\n' %
        (network_id, datetime.datetime.now())
    )
    net_out.write('-----------------------------------------------------\n\n')

    # --------- CREATION ---------
    net_out.write('--------- CREATION ---------\n')

    # Deploy VM
    request = {
        'serviceofferingid': service_offering_id,
        'templateid': template_id,
        'zoneid': zone_id,
        'networkids': network_id,
        'name': 'zone-test-%s-%d' % (network_id, time.time()),
        'displayname': 'zone-test-%s-%d' % (network_id, time.time()),
        'startvm': 'false',
    }

    result = api.deployVirtualMachine(request)

    if result == {} or 'jobid' not in result.keys():
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

    # Start VM
    request = {'id': vm_id}
    result = api.startVirtualMachine(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed job to start VM on network %s. '
            ' Response was %s\n' %
            (network_id, result),
        )
        return False
    net_out.write('Starting VM...\n')

    result = wait_for_job(result['jobid'], api)

    if result == {} or 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Failed to start VM on network %s.'
            ' Response was %s\n' % (network_id, result)
        )
        return False

    vm_password = result['virtualmachine']['password']
    net_out.write(
        'VM %s successfully started. ROOT password: %s.\n'
        % (vm_id, vm_password),
    )

    # Obtain EBS disk offering ID
    request = {}
    result = api.listDiskOfferings(request)

    for disk in result['diskoffering']:
        if disk['name'] == 'EBS':
            disk_offering_id = disk['id']

    # Check if EBS disk offering exists
    if disk_offering_id == '':
        net_out.write(
            'ERROR: Impossible create an EBS volume. No disk offering'
        )
        return False

    # Create volumes (ESB - 10GB)
    volume_name = ('zone_test_%s' % network_id)

    request = {
        'name': volume_name,
        'zoneid': zone_id,
        'diskofferingid': disk_offering_id,
        'size': 10,
    }
    result = api.createVolume(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed job to create volume on network %s. '
            ' Response was %s\n' %
            (network_id, result),
        )
        return False

    result = wait_for_job(result['jobid'], api)

    if result == {} or result['volume']['id'] == []:
        net_out.write(
            'ERROR: Failed to create volume on zone %s.'
            ' Response was %s\n' % (zone_id, result),
        )
        return False

    volume_id = result['volume']['id']
    net_out.write(
        'Volume %s successfully created on zone %s.\n'
        % (volume_id, zone_id)
    )

    # Attach volumes
    request = {
        'id': volume_id,
        'virtualmachineid': vm_id,
    }
    result = api.attachVolume(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed to create job to attach volume on VM %s. '
            ' Response was %s\n' %
            (vm_id, result),
        )
        return False

    result = wait_for_job(result['jobid'], api)
    if result == {} or result['volume']['virtualmachineid'] != vm_id:
        net_out.write(
            'ERROR: Failed to attach volume on VM %s.'
            ' Response was %s\n' % (vm_id, result),
        )
        return False

    net_out.write(
        'Volume %s successfully attached to VM %s.\n'
        % (volume_id, vm_id)
    )

    # Get public IP ID of isolated networks

    request = {'associatednetworkid': network_id}
    result = api.listPublicIpAddresses(request)
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
    # Set egress firewall for VM to ports 80/tcp and 53/udp
    egress_ids = []
    for port in ['80', '53']:
        if port == '53':
            protocol = 'UDP'
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
                ' Response was %s\n' % result,
            )
            return False

        egress_id = result['firewallrule']['id']
        egress_ids.append(egress_id)

        net_out.write(
            'egress firewall rule %s successfully created on network %s '
            'for port: %s/%s.\n'
            % (egress_id, network_id, port, protocol)
        )

    # Wait for the new Rules to apply
    time.sleep(5)

    # Suppress error messages from paramiko
    logging.getLogger('paramiko').addHandler(logging.NullHandler())

    # -------- ACTION ---------
    net_out.write('--------- ACTION ---------\n')

    # SSH to VM
    # Ensure that http works
    command = 'curl www.google.com'
    ssh_out = ssh_command(command, ip_address, vm_password, public_port)
    test = ('google' in ssh_out.lower())
    if test:
        net_out.write(
            'http//:www.google.com successfully reached.\n'
        )
    else:
        net_out.write(
            'ERROR: http//:www.google.com connection denied. Prompted: %s\n'
            % ssh_out,
        )
        return False

    # Ensure that https is denied
    command = 'curl --proto https www.google.com'
    ssh_out = ssh_command(command, ip_address, vm_password, public_port)
    test = ('https://www.google' not in ssh_out.lower())
    if test:
        net_out.write(
            'https//:www.google.com connection denied.\n'
        )
    else:
        net_out.write(
            'ERROR: https//:www.google.com successfully reached. '
            'Prompted: %s\n'
            % ssh_out,
        )
        return False

    # Rescan SCSI bus for discovering new attached volumes
    command = (
        'for controller in /sys/class/scsi_host/*; '
        'do echo "- - -"> $controller/scan; done'
    )
    ssh_command(command, ip_address, vm_password, public_port)

    # Format attached volumes
    command = 'mkfs.ext4 -F /dev/sdb'
    ssh_command(command, ip_address, vm_password, public_port)

    # Mount attached volumes
    command = (
        'mkdir /media/volume_test; '
        'mount /dev/sdb /media/volume_test'
    )
    ssh_command(command, ip_address, vm_password, public_port)

    # Check if Volumes are mounted
    command = 'mount'
    ssh_out = ssh_command(command, ip_address, vm_password, public_port)

    if '/dev/sdb ' in ssh_out:
        net_out.write(
            'Volume formatted and mounted.\n'
        )
    else:
        net_out.write(
            'ERROR: Volume not formatted or mounted properly.\n'
        )
        return False

    # Put file on volumes containing 'zonetest'
    command = 'touch /media/volume_test/zone_test'
    ssh_command(command, ip_address, vm_password, public_port)

    # Reboot
    command = 'reboot'
    ssh_command(command, ip_address, vm_password, public_port)
    net_out.write('Rebooting VM...\n')

    # Wait for reboot to start
    time.sleep(1)

    # SSH to VM
    command = 'echo "reboot completed"'
    ssh_out = ssh_command(command, ip_address, vm_password, public_port)
    if ssh_out is not '':
        net_out.write('VM successfully rebooted.\n')
    else:
        net_out.write('VM did not reboot correctly. Prompted: %s\n' % ssh_out)
        return False

    # Mount attached volumes
    command = 'mount /dev/sdb /media/volume_test'
    ssh_command(command, ip_address, vm_password, public_port)

    # Check data on volumes
    command = 'find /media/volume_test/zone_test'
    ssh_out = ssh_command(command, ip_address, vm_password, public_port)

    if 'zone_test' in ssh_out:
        net_out.write(
            "Volume's data appears to be OK.\n"
        )
    else:
        net_out.write(
            "ERROR: Volume's data corrupted.\n"
        )
        return False

    # Stop VM
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
    timeout = 30
    while counter < timeout:
        request = {
            'id': volume_id,
        }
        result = api.listVolumes(request)

        if 'virtualmachineid' not in result['volume'][0].keys():

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

    counter = 0
    while counter < timeout:
        request = {}
        result = api.listVolumes(request)
        volumesid = []
        for volume in result['volume']:
            volumesid.append(volume['id'])

        counter += 1
        if volume_id not in volumesid:
            net_out.write(
                'Volume successfully deleted.\n'
            )
            break
        elif counter == timeout:
            net_out.write(
                'ERROR: TimeOut. Failed to delete volume %s.'
                ' Response was %s\n' % (volume_id, result),
            )
        time.sleep(1)

    # Take VM snapshot
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

    if result == {} or result['vmsnapshot']['virtualmachineid'] != vm_id:
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

    # Start VM
    request = {'id': vm_id}
    result = api.startVirtualMachine(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed job to start VM on network %s. '
            ' Response was %s\n' %
            (network_id, result),
        )
        return False
    net_out.write('Starting VM...\n')

    result = wait_for_job(result['jobid'], api)

    if result == {} or 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Failed to start VM on network %s.'
            ' Response was %s\n' % (network_id, result)
        )
        return False
    net_out.write('VM successfully started.\n')

    # Put file in home directory containing 'zonetest'
    command = 'touch ~/zonetest'
    ssh_command(command, ip_address, vm_password, public_port)

    # Check that the file is present
    command = 'find ~/zonetest'
    ssh_out = ssh_command(command, ip_address, vm_password, public_port)
    if 'zonetest' in ssh_out:
        net_out.write(
            'File "zonetest" successfully put in home directory.\n'
        )
    else:
        net_out.write(
            'ERROR: File "zonetest" not put in home directory. Prompted: %s\n'
            % ssh_out,
        )
        return False

    # Stop VM
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

    # Revert VM to snapshot
    request = {
        'vmsnapshotid': vm_snapshot_id,
    }
    result = api.revertToVMSnapshot(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed to create job to revert VM %s from snapshot %s. '
            ' Response was %s\n'
            % (vm_id, vm_snapshot_id, result),
        )
        return False
    net_out.write('Reverting VM from snapshot...\n')

    result = wait_for_job(result['jobid'], api)

    if result == {} or result['virtualmachine']['id'] != vm_id:
        net_out.write(
            'ERROR: Failed  to revert VM %s from snapshot %s. '
            ' Response was %s\n'
            % (vm_id, vm_snapshot_id, result),
        )
        return False

    # Start VM
    request = {'id': vm_id}
    result = api.startVirtualMachine(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed to create job to start VM on network %s. '
            ' Response was %s\n' %
            (network_id, result),
        )
        return False
    net_out.write('Starting VM...\n')

    result = wait_for_job(result['jobid'], api)

    if result == {} or 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Failed to start VM on network %s.'
            ' Response was %s\n' % (network_id, result)
        )
        return False
    net_out.write('VM successfully started.\n')

    # Check that the file is absent
    command = 'find ~/zonetest'
    ssh_out = ssh_command(command, ip_address, vm_password, public_port)
    if 'zonetest' not in ssh_out:
        net_out.write(
            'VM successfully reverted from snapshot '
            '(File "zonetest" is not in home directory).\n'
        )
    else:
        net_out.write(
            'ERROR: VM snapshot %s not restored correctly. Prompted: %s\n'
            % (vm_snapshot_id, ssh_out),
        )
        return False

    # Get VM uptime, calculate last boot time
    command = "cat /proc/uptime|awk '{print $1}'"
    before = ssh_command(command, ip_address, vm_password, public_port)

    # Reboot VM
    request = {'id': vm_id}
    result = api.rebootVirtualMachine(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed to create job to reboot VM on network %s. '
            ' Response was %s\n' % (network_id, result),
        )
        return False
    net_out.write('Rebooting VM...\n')

    result = wait_for_job(result['jobid'], api)

    if result == {} or 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Failed to reboot VM on network %s.'
            ' Response was %s\n' % (network_id, result),
        )
        return False

    # SSH to VM
    command = "cat /proc/uptime|awk '{print $1}'"
    after = ssh_command(command, ip_address, vm_password, public_port)

    # Check if machine successfully rebooted
    if after < before:
        net_out.write('VM successfully rebooted.\n')
    else:
        net_out.write('VM din not reboot correctly.\n')

    # Stop VM
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

    # Reset VM password
    request = {
        'id': vm_id,
    }
    result = api.resetPasswordForVirtualMachine(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed job to reset VM password. '
            ' Response was %s\n' % result,
        )
        return False
    net_out.write('Resetting VM password...\n')

    result = wait_for_job(result['jobid'], api)

    if result == {} or 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Failed to reset VM password. '
            ' Response was %s\n' % result,
        )
        return False

    # Define VM password
    vm_password = result['virtualmachine']['password']

    # Start VM
    request = {'id': vm_id}
    result = api.startVirtualMachine(request)

    if result == {} or 'jobid' not in result.keys():
        net_out.write(
            'ERROR: Failed job to start VM on network %s. '
            ' Response was %s\n' %
            (network_id, result),
        )
        return False
    net_out.write('Starting VM...\n')

    result = wait_for_job(result['jobid'], api)

    if result == {} or 'virtualmachine' not in result:
        net_out.write(
            'ERROR: Failed to start VM on network %s.'
            ' Response was %s\n' % (network_id, result)
        )
        return False
    net_out.write('VM successfully started.\n')

    # SSH to VM with new password
    command = 'echo "password reset"'
    ssh_out = ssh_command(command, ip_address, vm_password, public_port)

    if 'password reset' in ssh_out:
        net_out.write(
            'Password reset correctly. ROOT password: %s\n'
            % vm_password,
        )
    else:
        net_out.write(
            'The password was not reset correctly. '
            'Prompted: %s\n' % ssh_out,
        )

    # --------- DELETION ---------
    net_out.write('--------- DELETION ---------\n')

    # Shutdown
    command = 'shutdown -h now'
    ssh_out = ssh_command(command, ip_address, vm_password, public_port)
    net_out.write('Shutting down VM...\n')

    # Wait for shutdown to start
    time.sleep(1)

    # Check Shoutdown
    command = 'echo hello'
    ssh_out = ssh_command(command, ip_address, vm_password, public_port)
    if ssh_out is '':
        net_out.write('VM successfully shut down.\n')
    else:
        net_out.write('VM did not shutdown correctly.\n')
        return False

    # Remove port fowarding rule
    request = {'id': portforward_id}
    result = api.deletePortForwardingRule(request)
    result = wait_for_job(result['jobid'], api)

    # ERROR_HANDLING

    if result == {} or result['success'] == 'False':
        net_out.write(
            'ERROR: Failed to delete port forwarding rule on network %s.'
            'Response was %s\n' %
            (network_id, result),
        )
        return False
    net_out.write(
        'The port forwarding rule has been successfully removed.\n'
    )

    # Remove egress firewall rules
    for egress_id in egress_ids:
        request = {'id': egress_id}
        result = api.deleteEgressFirewallRule(request)
        result = wait_for_job(result['jobid'], api)
        # ERROR_HANDLING

        if result == {} or result['success'] == 'False':
            net_out.write(
                'ERROR: Failed to delete egress firewall rule on network %s.'
                'Response was %s\n' %
                (network_id, result),
            )
            return False
        net_out.write(
            'The egress firewall rule have been successfully removed.\n'
        )

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
        time.sleep(1)

    # Expunge VM
    request = {
        'id': vm_id,
        'expunge': 'true',
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

        time.sleep(1)

    # Everything has been successfull (if we get here)
    return True

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

    parser.add_argument(
        '-t', '--template',
        dest='template_name',
        type=str,
        choices=template_names,
        default='Centos 6.4 (64-bit)',
        help='The template name.'
             ' You must select a template that runs linux with ssh enabled.'
             ' It must also have the password reset enabled.'
    )

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
        '-u', '--usernumber',
        dest='user_number',
        type=int,
        default=5,
        help='Number of users',
    )

    parser.add_argument(
        '-n', '--vmnumber',
        dest='vm_number',
        type=int,
        default=5,
        help='Number of vms per network',
    )



    parser.add_argument(
        '-v', '--validate',
	dest='validate',
	action="store_true",
        help="Validate the networks ;-)",
    )


    args = parser.parse_args()
    # Assign parsed arguments
    zone_name = args.zone_name
    template_name = args.template_name
    base_username = args.base_username
    parent_domain = args.parent_domain
    user_number = args.user_number
    vm_number = args.vm_number
    compute_service_offering = args.service_offering


    # Obtain zone ID
    for zone in zone_result['zone']:
        if zone['name'] == zone_name:
            zone_id = zone['id']
            break

    # Check if template is present in selected zone
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
            break
    if template_id is None:
        sys.stderr.write(
            'The template is not available in the selected zone.\n'
            'The following templates are available:\n'
        )
        for template in temp_result['template']:
            print(template['name'])
        sys.exit()


    ### We get the ID of the parent domain ### 

    request = {
        'name': parent_domain
    }

    parentdomain_result = api.listDomains(request)
    parentdomain_id = parentdomain_result['domain'][0]['id']

    print("Parent domain id: %s" % parentdomain_id)

    ### list to keep track of the domain_ids and user_ids

    domain_ids = {}
    account_ids = {}
    user_ids = {}

    ### Creating domains and users ###

    user_sep="-"
    domain_sep="/"

    for num in range(1,(user_number+1)):    
	### Create the username
        user_name=user_sep.join((base_username,zone_name,str(num)))
        print( "User name is %s" % user_name )
        domain_id=create_domainanduser(user_name,parentdomain_id)



    
    ### Create a network and some vms for each of the users ###

    ### Check Service offering
    ### Service offering ids

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

    for key in domain_ids:
        user_name=key
        domain_id=domain_ids[user_name]
        print ( 'user name %s:' % user_name )
        account_id=account_ids[user_name]
        network_name='net-'+user_name
        displaytext=network_name
        ### First we create the networks
        network_ids[user_name]=create_network(zone_id, domain_id, displaytext, network_name, account_id, api)
        ### Then we create a parallel process for the vms
        output(
            message='created network with IDs: %s' %
            ','.join(network_ids),
            )
        for number in range(1,(vm_number+1)):
            vm_name='vm-'+user_name+str(number)
            ###vm_ids[vm_name]=deploy_vm(zone_id, network_ids[user_name],template_id, api, vm_name, user_name, domain_id, service_offering_id)
            process = multiprocessing.Process(target=deploy_vm, args=(
                zone_id,
                network_ids[user_name],
                template_id,
                api,
                vm_name, 
                user_name,
                domain_id,
                service_offering_id
                ),
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
        
