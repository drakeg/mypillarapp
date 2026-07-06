output "public_ip" {
  value = module.ec2.public_ip
}

output "public_dns" {
  value = module.ec2.public_dns
}

output "instance_id" {
  value = module.ec2.instance_id
}

output "elastic_ip" {
  value = module.ec2.elastic_ip
}

output "primary_domain" {
  value = var.primary_domain
}

output "ami_id" {
  value = module.ec2.ami_id
}

output "ami_family" {
  value = var.ami_family
}

output "ssh_user" {
  value = module.ec2.ssh_user
}

output "security_group_id" {
  value = module.security.web_security_group_id
}

output "security_baseline_document_name" {
  value = module.ssm.security_baseline_document_name
}

output "security_baseline_association_id" {
  value = module.ssm.security_baseline_association_id
}

output "app_deploy_document_name" {
  value = module.app_deploy.app_deploy_document_name
}

output "app_deploy_association_id" {
  value = module.app_deploy.app_deploy_association_id
}

output "app_deploy_hash" {
  value = module.app_deploy.app_deploy_hash
}

output "site_artifact_bucket_name" {
  value = module.app_deploy.artifact_bucket_name
}

output "ses_domain_identity_name" {
  value = module.ses.ses_domain_identity_name
}

output "ses_external_dns_records" {
  value       = module.ses.external_dns_records
  description = "DNS records to add at your external DNS provider for SES verification/DKIM/SPF/DMARC."
}

output "ses_sandbox_note" {
  value = module.ses.ses_sandbox_note
}
