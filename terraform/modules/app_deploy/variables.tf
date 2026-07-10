variable "project_name" {
  type = string
}

variable "primary_domain" {
  type = string
}

variable "additional_domains" {
  type    = list(string)
  default = []
}

variable "acme_email" {
  type = string
}

variable "admin_username_parameter_name" {
  type        = string
  description = "SSM parameter name containing the admin username."
}

variable "admin_password_hash_parameter_name" {
  type        = string
  description = "SSM SecureString parameter name containing the admin password hash."
}

variable "admin_session_secret_parameter_name" {
  type        = string
  description = "SSM SecureString parameter name containing the admin session secret."
}

variable "admin_token_parameter_name" {
  type        = string
  description = "Optional SSM SecureString parameter name containing the legacy admin token."
}

variable "enable_email_notifications" {
  type        = bool
  default     = false
  description = "Whether the app should send SES email notifications for leads and chat messages."
}

variable "notify_email_from" {
  type        = string
  default     = ""
  description = "Verified SES sender email address."
}

variable "notify_email_to" {
  type        = string
  default     = ""
  description = "Destination email address for admin notifications."
}

variable "ses_identity_arn" {
  type        = string
  default     = ""
  description = "Optional SES identity ARN to scope send permissions. When blank and email is enabled, permissions fall back to '*'."
}

variable "site_source_dir" {
  type        = string
  description = "Local path to the site files that should be uploaded as deployment artifacts."
}

variable "instance_role_name" {
  type        = string
  description = "IAM role name attached to the EC2 instance so it can read site artifacts from S3."
}

variable "target_tag_key" {
  type    = string
  default = "MadMallardPlatform"
}

variable "target_tag_value" {
  type    = string
  default = "true"
}

variable "tags" {
  type    = map(string)
  default = {}
}
