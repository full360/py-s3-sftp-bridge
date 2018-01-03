output "lambda_zip" {
  value = "${path.module}/${data.external.get_filename.result.zip_file}"
}
