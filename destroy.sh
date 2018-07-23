#!/bin/sh

. ./lib.sh

ansible-playbook $COMMON_ANSIBLE_VARS destroy.yml
