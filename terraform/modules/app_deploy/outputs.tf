output "app_deploy_document_name" {
  value = aws_ssm_document.app_deploy.name
}

output "app_deploy_association_id" {
  value = aws_ssm_association.app_deploy.association_id
}


output "artifact_bucket_name" {
  value = aws_s3_bucket.artifacts.bucket
}
