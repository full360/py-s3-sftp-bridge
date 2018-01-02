# This Terraform script allows the repo to be used as a terraform module

resource "null_resource" "compile_py" {
  triggers {
    main         = "${base64sha256(file("${path.module}/s3_sftp_bridge.py"))}"
    requirements = "${base64sha256(file("${path.module}/requirements.txt"))}"
  }

  provisioner "local-exec" {
    command = "make docker"
  }
}
