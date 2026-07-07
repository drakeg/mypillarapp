variable "aws_region" {
  type        = string
  description = "AWS region to deploy into."
  default     = "us-east-1"
}

variable "project_name" {
  type        = string
  description = "Project/application name used for tags and resource names."
  default     = "madmallard-platform"
}

variable "environment" {
  type        = string
  description = "Logical environment name. Only prod is intended to be deployed for now."
  default     = "prod"
}

variable "primary_domain" {
  type        = string
  description = "The test/production hostname to serve, for example pillar.madmallards.com."

  validation {
    condition     = length(trimspace(var.primary_domain)) > 0
    error_message = "primary_domain must not be empty. Use a test hostname such as pillar.madmallards.com."
  }
}

variable "additional_domains" {
  type        = list(string)
  description = "Additional hostnames Caddy should serve."
  default     = []
}

variable "acme_email" {
  type        = string
  description = "Email used for ACME/Let's Encrypt certificate registration."

  validation {
    condition     = length(trimspace(var.acme_email)) > 0
    error_message = "acme_email must not be empty."
  }
}

variable "public_key" {
  type        = string
  description = "Legacy single SSH public key. Prefer ssh_public_keys for multiple systems."
  default     = ""
}

variable "ssh_public_keys" {
  type        = list(string)
  description = "SSH public keys allowed to access the instance from multiple systems."
  default     = []
}

variable "ssh_cidr" {
  type        = string
  description = "CIDR allowed for SSH. Use your-public-ip/32. Set empty to disable SSH ingress."
  default     = ""
}

variable "instance_type" {
  type        = string
  description = "EC2 instance type. t3.micro is x86 Free Tier eligible in many accounts; t4g.micro is cheaper ARM when not Free Tier."
  default     = "t3.micro"
}

variable "ami_family" {
  type        = string
  description = "AMI family to use when ami_id is empty."
  default     = "amazon-linux-2023"

  validation {
    condition     = contains(["amazon-linux-2023", "ubuntu-24.04", "ubuntu-22.04"], var.ami_family)
    error_message = "ami_family must be amazon-linux-2023, ubuntu-24.04, or ubuntu-22.04."
  }
}

variable "ami_id" {
  type        = string
  description = "Optional pinned AMI ID. Leave empty to discover the latest AMI for ami_family."
  default     = ""
}

variable "root_volume_size" {
  type        = number
  description = "Root EBS volume size in GB."
  default     = 20
}

variable "security_profile" {
  type        = string
  description = "Security baseline profile applied by SSM."
  default     = "standard"

  validation {
    condition     = contains(["minimal", "standard", "hardened"], var.security_profile)
    error_message = "security_profile must be minimal, standard, or hardened."
  }
}


variable "use_elastic_ip" {
  type        = bool
  description = "Whether to allocate and associate an Elastic IP. Defaults false to minimize cost. Enable later for stable DNS."
  default     = false
}

variable "user_data_replace_on_change" {
  type        = bool
  description = "Whether user_data changes should replace the EC2 instance. Defaults false to avoid accidental IP changes."
  default     = false
}

variable "enable_ssh" {
  type        = bool
  description = "Whether to allow inbound SSH. Keep true for now; set false later if using SSM-only access."
  default     = true
}

variable "admin_token" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Optional admin inbox token. Leave blank to disable /admin/inbox."
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
  description = "Secret used to sign admin sessions/cookies. Should be a long random value when password login is enabled."
}


variable "enable_email_notifications" {
  type        = bool
  default     = false
  description = "Enable SES email notifications for contact forms and chat."
}

variable "notify_email_from" {
  type        = string
  default     = ""
  description = "Verified SES sender email address, e.g. no-reply@madmallards.com."
}

variable "notify_email_to" {
  type        = string
  default     = ""
  description = "Where admin notifications should be sent."
}

variable "ses_domain" {
  type        = string
  default     = "madmallards.com"
  description = "Domain to verify in SES. DNS is external, so Terraform outputs records to add manually."
}

variable "create_ses_recipient_identity" {
  type        = bool
  default     = true
  description = "Create SES email identity for notify_email_to so SES sandbox testing can work after email confirmation."
}


variable "enable_custom_mail_from" {
  type        = bool
  default     = true
  description = "Create SES custom MAIL FROM configuration. Requires adding output DNS records at external DNS provider."
}

variable "mail_from_subdomain" {
  type        = string
  default     = "mail"
  description = "Subdomain for SES custom MAIL FROM, e.g. mail creates mail.madmallards.com."
}
