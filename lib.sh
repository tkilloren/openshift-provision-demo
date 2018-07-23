#!/bin/sh

CLUSTER_NAME="$1"
USAGE="Usage: $0 <CLUSTER_NAME>"

if [ "$CLUSTER_NAME" == "" ]; then
  echo -e "No cluster name provided.\n$USAGE" >&2
  exit 1
fi

. env/$CLUSTER_NAME.sh

CLOUD_PROVIDER=$(sed -n 's/^cloud_provider: //p' $OPENSHIFT_CLUSTER_CONFIG/cluster/$OPENSHIFT_CLUSTER_NAME/vars/main.yml)

COMMON_ANSIBLE_VARS="
-i $CLOUD_PROVIDER-hosts.py \
-e cluster_name=$CLUSTER_NAME \
-e openshift_master_cluster_public_certfile=$PWD/tls/$CLUSTER_NAME-master.cert \
-e openshift_master_cluster_public_keyfile=$PWD/tls/$CLUSTER_NAME-master.key \
-e openshift_master_cluster_public_cafile=$PWD/tls/$CLUSTER_NAME-master.ca"
