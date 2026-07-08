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

variable "admin_token" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Optional admin inbox token for /admin/inbox?token=... . Leave blank to disable the web inbox."
}
variable "admin_username" {
  type        = string
  default     = "admin"
  description = "Admin login username."
}

variable "admin_password_hash" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Optional admin password hash for admin login. Leave blank to use token-only admin access."
}

variable "admin_session_secret" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Secret used to sign admin sessions/cookies."
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
