data "external" "get_filename" {
  program = ["bash", "-c", "${path.module}/make", "terraform_zip" ]
}
