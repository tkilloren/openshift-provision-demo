#!/usr/bin/env python

from __future__ import print_function

import os
import sys

import openshift_gcp

def exit_usage(msg=''):
    print(msg + """
Usage: gcp-hosts --list
   Or: gcp-hosts --host <HOSTNAME>
   Or: gcp-hosts --wait <TIMEOUT_SECONDS>

Environment Variables:
OPENSHIFT_CLUSTER_CONFIG - Location of cluster configuration
OPENSHIFT_CLUSTER_NAME - Name of cluster in configuration
""",
    file=sys.stderr)
    sys.exit(1)

def main():
    ocpgcp = openshift_gcp.OpenShiftGCP()
    if( 'OPENSHIFT_CLUSTER_CONFIG' not in os.environ ):
        exit_usage('OPENSHIFT_CLUSTER_CONFIG environment variable not set.')
    elif( 'OPENSHIFT_CLUSTER_NAME' not in os.environ ):
        exit_usage('OPENSHIFT_CLUSTER_NAME environment variable not set.')

    ocpgcp.load_cluster_config(
        config_dir = os.environ['OPENSHIFT_CLUSTER_CONFIG'],
        cluster_name = os.environ['OPENSHIFT_CLUSTER_NAME']
    )

    if len(sys.argv) == 2 and sys.argv[1] == '--list':
        ocpgcp.print_host_list_json()
    elif len(sys.argv) == 3 and sys.argv[1] == '--host':
        ocpgcp.print_host_json(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == '--wait':
        ocpgcp.wait_for_hosts_running(int(sys.argv[2]))
    else:
        exit_usage()

if __name__ == '__main__':
    main()
