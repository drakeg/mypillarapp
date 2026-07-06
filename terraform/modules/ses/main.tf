variable "project_name" {
  type = string
}

variable "enabled" {
  type        = bool
  default     = false
  description = "Whether to create SES identities and email DNS verification outputs."
}

variable "ses_domain" {
  type        = string
  default     = ""
  description = "Domain to verify in SES, e.g. madmallards.com. Required when enabled=true."
}

variable "notify_email_to" {
  type        = string
  default     = ""
  description = "Optional destination email identity to verify for SES sandbox testing."
}

variable "create_recipient_identity" {
  type        = bool
  default     = true
  description = "Create an SES email identity for notify_email_to so sandbox test recipients can be verified."
}

variable "tags" {
  type    = map(string)
  default = {}
}

locals {
  create_domain_identity    = var.enabled && length(trimspace(var.ses_domain)) > 0
  create_recipient_identity = var.enabled && var.create_recipient_identity && length(trimspace(var.notify_email_to)) > 0
}

resource "aws_ses_domain_identity" "this" {
  count  = local.create_domain_identity ? 1 : 0
  domain = var.ses_domain
}

resource "aws_ses_domain_dkim" "this" {
  count  = local.create_domain_identity ? 1 : 0
  domain = aws_ses_domain_identity.this[0].domain
}

resource "aws_ses_email_identity" "recipient" {
  count = local.create_recipient_identity ? 1 : 0
  email = var.notify_email_to
}

locals {
  verification_txt_record = local.create_domain_identity ? {
    name  = "_amazonses.${var.ses_domain}"
    type  = "TXT"
    value = aws_ses_domain_identity.this[0].verification_token
  } : null

  dkim_cname_records = local.create_domain_identity ? [
    for token in aws_ses_domain_dkim.this[0].dkim_tokens : {
      name  = "${token}._domainkey.${var.ses_domain}"
      type  = "CNAME"
      value = "${token}.dkim.amazonses.com"
    }
  ] : []

  spf_txt_record = local.create_domain_identity ? {
    name  = var.ses_domain
    type  = "TXT"
    value = "v=spf1 include:amazonses.com ~all"
  } : null

  dmarc_txt_record = local.create_domain_identity ? {
    name  = "_dmarc.${var.ses_domain}"
    type  = "TXT"
    value = "v=DMARC1; p=none; rua=mailto:postmaster@${var.ses_domain}"
  } : null
}

output "ses_domain_identity_arn" {
  value = local.create_domain_identity ? aws_ses_domain_identity.this[0].arn : ""
}

output "ses_domain_identity_name" {
  value = local.create_domain_identity ? aws_ses_domain_identity.this[0].domain : ""
}

output "ses_recipient_identity_arn" {
  value = local.create_recipient_identity ? aws_ses_email_identity.recipient[0].arn : ""
}

output "external_dns_records" {
  description = "DNS records to add at the external DNS provider for SES verification and authentication."
  value = local.create_domain_identity ? {
    verification_txt = local.verification_txt_record
    dkim_cnames      = local.dkim_cname_records
    recommended_spf  = local.spf_txt_record
    recommended_dmarc = local.dmarc_txt_record
  } : null
}

output "ses_sandbox_note" {
  value = var.enabled ? "If your SES account is in sandbox, confirm the verification email sent to notify_email_to and request SES production access before emailing unverified visitors." : "SES disabled."
}
