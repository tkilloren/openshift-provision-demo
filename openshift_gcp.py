#!/usr/bin/env python

import googleapiclient.discovery
import googleapiclient.errors
import jinja2
import json
import os
import re
import time
import yaml

class OpenShiftGCP:
    def __init__(self):
        self.computeAPI = googleapiclient.discovery.build('compute', 'v1')

    def load_cluster_main(self):
        for file_extension in ['yaml','yml','json']:
            try:
                return yaml.load(
                    file('/'.join([
                        self.config_dir,
                        'cluster',
                        self.cluster_name,
                        'vars/main.' + file_extension
                    ]), 'r')
                )
            except IOError:
                pass
        raise Exception("Unable to load main cluster configuration file.")

    def load_cluster_vars(self, subdir, entry='.'):
        vardir = '/'.join([self.config_dir, subdir, entry, 'vars'])
        for varfile in os.listdir(vardir):
            if not re.match(r'\w.*\.(ya?ml|json)$', varfile):
                continue
            varpath = '/'.join([vardir, varfile])
            self.cluster_config.update(yaml.load(file(varpath,'r')))

    def load_cluster_config(self, config_dir, cluster_name):
        self.config_dir = config_dir
        self.cluster_name = cluster_name
        self.cluster_config = {}
        cluster_main = self.load_cluster_main()
        self.load_cluster_vars('default')
        self.load_cluster_vars('cloud_provider', cluster_main['cloud_provider'])
        self.load_cluster_vars('cloud_region', cluster_main['cloud_region'])
        self.load_cluster_vars('cluster', self.cluster_name)

    def cluster_var(self, varname):
        value = self.cluster_config[varname]
        if value is str:
            t = jinja2.Template(self.cluster_config[varname])
            return t.render(self.cluster_config)
        else:
            return value

    def instance_fqdn(self, instance):
        return '%s.c.%s.internal' % (
            instance['name'],
            self.cluster_var('openshift_gcp_project')
        )



    def instance_belongs_to_cluster(self, instance):
        return(
            'openshift-cluster' in instance['labels'] and
            self.cluster_name == instance['labels']['openshift-cluster']
        )

    def get_instance(self, hostname):
        for zone in self.cluster_var('openshift_gcp_zones'):
            try:
                instance = self.computeAPI.instances().get(
                    instance = hostname.split('.')[0],
                    project = self.cluster_var('openshift_gcp_project'),
                    zone = zone
                ).execute()
            except googleapiclient.errors.HttpError:
                continue
            if self.instance_belongs_to_cluster(instance):
                return instance
            return None
        return None

    def get_cluster_instances(self):
        for zone in self.cluster_var('openshift_gcp_zones'):
            for instance in self.get_cluster_instances_in_zone(zone):
                yield instance

    def get_cluster_instances_in_zone(self, zone):
        for instance in self.get_instances_in_zone(zone):
            if self.instance_belongs_to_cluster(instance):
                yield instance

    def get_instances_in_zone(self, zone):
        req = self.computeAPI.instances().list(
            project = self.cluster_var('openshift_gcp_project'),
            zone = zone
        )
        while req:
            resp = req.execute()
            for instance in resp.get('items', []):
                yield instance
            req = self.computeAPI.instances().list_next(
                previous_request = req,
                previous_response = resp
            )

    def instance_ansible_host_groups(self, instance):
        groups = []
        for item in instance['metadata']['items']:
            if( item['key'].startswith('ansible-host-group-')
            and item['value'] == 'true'):
                groups.append(item['key'][19:])
        if groups:
            return groups
        else:
            # Did not find any ansible-host-group-* metadata, default to nodes
            return ['nodes']

    def instance_openshift_node_group_name(self, instance):
        name = instance['labels'].get('openshift-node-group-name', 'compute')
        # Drop useless "node-config-" prefix if present
        if name.startswith('node-config-'):
            return name[12:]
        return name

    def instance_openshift_node_labels(self, instance):
        node_labels = {
            'failure-domain.beta.kubernetes.io/region':
                self.cluster_var('openshift_gcp_region'),
            'failure-domain.beta.kubernetes.io/zone':
                instance['zone'].rsplit('/',1)[1]
        }

        node_group_name = self.instance_openshift_node_group_name(instance)
        node_group_labels = self.cluster_config \
            .get('openshift_provision_node_groups', {}) \
            .get(node_group_name, {}) \
            .get('labels', {'node-role.kubernetes.io/'+node_group_name: 'true' })
        node_labels.update(node_group_labels)
        return node_labels

    def instance_ansible_host_ip(self, instance):
        primary_network_interface = instance['networkInterfaces'][0]
        try:
            return primary_network_interface['accessConfigs'][0]['natIP']
        except (IndexError, KeyError):
            return primary_network_interface['networkIP']

    def instance_add_host_storage_devices(self, instance, hostvars):
        glusterfs_devices = []
        for disk in instance['disks']:
            device =  '/dev/disk/by-id/google-' + disk['deviceName']
            if re.match(r'docker(-?vg)?$', disk['deviceName']):
                hostvars['container_runtime_docker_storage_setup_device'] = device
            elif disk['deviceName'].startswith('glusterfs-'):
                glusterfs_devices.append(device)
        if len(glusterfs_devices) > 0:
            hostvars['glusterfs_devices'] = glusterfs_devices

    def instance_add_ansible_vars(self, instance, hostvars):
        for item in instance['metadata']['items']:
            if item['key'].startswith('ansible-var-'):
                try:
                    value = json.loads(item['value'])
                except:
                    value = item['value']
                hostvars[item['key'][12:]] = value

        return hostvars

    def instance_host_vars(self, instance):
        hostvars = {
            'ansible_host': self.instance_ansible_host_ip(instance),
            'openshift_node_group_name': 'node-config-' + self.instance_openshift_node_group_name(instance),
            'openshift_node_labels': self.instance_openshift_node_labels(instance)
        }
        self.instance_add_host_storage_devices(instance, hostvars)
        self.instance_add_ansible_vars(instance, hostvars)
        return hostvars

    def openshift_role_filter(self, hostvars):
        if 'OPENSHIFT_ROLE_FILTER' not in os.environ:
            return True
        for role in os.environ['OPENSHIFT_ROLE_FILTER'].split(','):
            kuberole = 'node-role.kubernetes.io/' + role
            if kuberole in hostvars['openshift_node_labels']:
                return True
        return False

    def print_host_json(self, hostname):
        instance = self.get_instance(hostname)

        if not instance or instance['status'] != 'RUNNING':
            print('{}')
            return

        print(json.dumps(self.instance_host_vars(instance)))

    def print_host_list_json(self):
        hosts = {
            'OSEv3': {
                'children': ['etcd', 'nodes'],
                'hosts': [],
                'vars': {
                    'ansible_become': True,
                    'ansible_user': 'cloud-user'
                }
            },
            'nodes': {
                'children': ['masters'],
                'hosts': []
            },
            'masters': {
                'hosts': []
            },
            '_meta': {
                'hostvars': {}
            }
        }

        for instance in self.get_cluster_instances():
            # Skip instances that are not running
            if instance['status'] != 'RUNNING':
                continue
            hostvars = self.instance_host_vars(instance)

            if not self.openshift_role_filter(hostvars):
                continue

            fqdn = self.instance_fqdn(instance)
            hosts['_meta']['hostvars'][fqdn] = hostvars

            for group in self.instance_ansible_host_groups(instance):
                if group in hosts:
                    hosts[group]['hosts'].append(fqdn)
                else:
                    hosts[group] = {
                        'hosts': [fqdn]
                    }

        # Put etcd on masters if separate etcd nodes were not indicated
        if 'etcd' not in hosts:
            hosts['etcd'] = {
                'children': ['masters']
            }

        print(json.dumps(hosts))

    def wait_for_hosts_running(self, timeout):
        start_time = time.time()
        all_ready = False
        instance_name = ''
        instance_status = ''
        while timeout > time.time() - start_time:
            try:
                for instance in self.get_cluster_instances():
                    instance_name = instance['name']
                    instance_status = instance['status']
                    if instance['status'] != 'RUNNING':
                        raise Exception(
                            "Instance %s not status RUNNING" % (instance_name)
                        )
                all_ready = True
            except:
                pass
            if all_ready:
                break
            print("Waiting for all instances to be RUNNING")
            time.sleep(2)
        if not all_ready:
            raise Exception("Instance %s found with status %s" % (instance_name, instance_status))

def main():
    ocpgcp = OpenShiftGCP()

if __name__ == '__main__':
    main()
