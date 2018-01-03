#!/bin/bash

# This script builds the zip file and passes the zip file
# back as a json string to be used by the external data provider
# in main.tf
cd "$(dirname "$0")"
make docker > /dev/null 2>&1
jq -n \
  --arg zip_file s3-sftp-bridge.zip \
	    '{"zip_file":$zip_file}'
