locals {
  combined_ssh_public_keys = distinct(compact(concat(var.ssh_public_keys, var.public_key != "" ? [var.public_key] : [])))

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

module "networking" {
  source       = "../../modules/networking"
  project_name = var.project_name
  tags         = local.tags
}

module "security" {
  source       = "../../modules/security"
  project_name = var.project_name
  vpc_id       = module.networking.vpc_id
  ssh_cidr     = var.ssh_cidr
  enable_ssh   = var.enable_ssh
  tags         = local.tags
}

module "iam" {
  source       = "../../modules/iam"
  project_name = var.project_name
  tags         = local.tags
}

module "ec2" {
  source                       = "../../modules/ec2"
  project_name                 = var.project_name
  environment                  = var.environment
  subnet_id                    = module.networking.public_subnet_id
  security_group_ids           = [module.security.web_security_group_id]
  instance_profile_name        = module.iam.instance_profile_name
  public_key                   = length(local.combined_ssh_public_keys) > 0 ? local.combined_ssh_public_keys[0] : ""
  instance_type                = var.instance_type
  ami_family                   = var.ami_family
  ami_id                       = var.ami_id
  root_volume_size             = var.root_volume_size
  primary_domain               = var.primary_domain
  additional_domains           = var.additional_domains
  acme_email                   = var.acme_email
  security_profile             = var.security_profile
  use_elastic_ip               = var.use_elastic_ip
  user_data_replace_on_change  = var.user_data_replace_on_change
  tags                         = local.tags
}


module "ssh_keys" {
  source          = "../../modules/ssh_keys"
  project_name    = var.project_name
  ssh_public_keys = local.combined_ssh_public_keys
  target_tag_key   = "MadMallardPlatform"
  target_tag_value = "true"
  tags            = local.tags

  depends_on = [module.ec2]
}

module "ssm" {
  source            = "../../modules/ssm"
  project_name      = var.project_name
  security_profile  = var.security_profile
  target_tag_key    = "MadMallardPlatform"
  target_tag_value  = "true"
  tags              = local.tags

  depends_on = [module.ec2]
}


module "ses" {
  source                    = "../../modules/ses"
  project_name              = var.project_name
  enabled                   = var.enable_email_notifications
  ses_domain                = var.ses_domain
  notify_email_to           = var.notify_email_to
  create_recipient_identity = var.create_ses_recipient_identity
  enable_custom_mail_from   = var.enable_custom_mail_from
  mail_from_subdomain       = var.mail_from_subdomain
  tags                      = local.tags
}

module "app_deploy" {
  source             = "../../modules/app_deploy"
  project_name       = var.project_name
  primary_domain     = var.primary_domain
  additional_domains = var.additional_domains
  acme_email         = var.acme_email
  admin_token                = var.admin_token
  admin_username             = var.admin_username
  admin_password_hash        = var.admin_password_hash
  admin_session_secret       = var.admin_session_secret
  enable_email_notifications = var.enable_email_notifications
  notify_email_from          = var.notify_email_from
  notify_email_to            = var.notify_email_to
  ses_identity_arn           = module.ses.ses_domain_identity_arn
  site_source_dir            = "${path.root}/../../../site/solutions"
  instance_role_name = module.iam.instance_role_name
  target_tag_key     = "MadMallardPlatform"
  target_tag_value   = "true"
  tags               = local.tags

  depends_on = [module.ec2, module.ses]
}
