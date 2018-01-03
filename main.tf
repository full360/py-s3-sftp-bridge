data "external" "get_filename" {
  program = ["bash", "-c", "${path.module}/terraform_helper.sh" ]
}
