data "external" "get_filename" {
  program = ["bash", "-c", "cd ${path.module} && make docker > ./build.log 2>&1 && jq -n --arg zip_file s3-sftp-bridge.zip '{\"zip_file\":$zip_file}'" ]
}
