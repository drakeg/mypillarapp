data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  domains = concat([var.primary_domain], var.additional_domains)

  caddy_sites = join("\n\n", [for domain in local.domains : <<-SITE
${domain} {
    encode zstd gzip
    reverse_proxy host.docker.internal:8000
}
SITE
  ])

  caddyfile = <<-CADDY
{
    email ${var.acme_email}
}

${local.caddy_sites}
CADDY

  all_site_files = fileset(var.site_source_dir, "**/*")

  site_files = [
    for file in local.all_site_files : file
    if !startswith(file, "__pycache__/")
    && !strcontains(file, "/__pycache__/")
    && !endswith(file, ".pyc")
    && !startswith(basename(file), ".")
  ]

  site_file_hashes = [
    for file in local.site_files : filesha256("${var.site_source_dir}/${file}")
  ]

  artifact_bucket_name = lower("${var.project_name}-${data.aws_caller_identity.current.account_id}-${data.aws_region.current.name}-site-artifacts")
  artifact_prefix      = "solutions"
  caddyfile_b64        = base64encode(local.caddyfile)
  admin_config_json    = jsonencode({
    admin_token          = var.admin_token
    admin_username       = var.admin_username
    admin_password_hash  = var.admin_password_hash
    admin_session_secret = var.admin_session_secret
  })
  deploy_hash          = sha256(join("\n", concat(local.site_file_hashes, [local.caddyfile, var.primary_domain, var.admin_username, var.admin_password_hash, var.admin_session_secret])))

  deploy_script = <<-SCRIPT
#!/usr/bin/env bash
set -euxo pipefail
LOG=/var/log/madmallard-app-deploy.log
exec > >(tee -a "$LOG") 2>&1

echo "[$(date -Is)] Mad Mallard app deployment starting"

if ! command -v aws >/dev/null 2>&1; then
  if command -v dnf >/dev/null 2>&1; then
    dnf install -y --refresh awscli || dnf install -y --allowerasing awscli
  elif command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y awscli
  else
    echo "No supported package manager found to install awscli" >&2
    exit 1
  fi
fi

mkdir -p /opt/madmallard-platform/app /opt/madmallard-platform/data /opt/madmallard-platform/caddy/data /opt/madmallard-platform/caddy/config

aws s3 sync "s3://${local.artifact_bucket_name}/${local.artifact_prefix}/" /opt/madmallard-platform/app/ --delete

cat > /opt/madmallard-platform/data/admin_config.json <<'ADMINCONFIG'
${local.admin_config_json}
ADMINCONFIG
chmod 600 /opt/madmallard-platform/data/admin_config.json

cat > /opt/madmallard-platform/caddy/Caddyfile.b64 <<'CADDYB64'
${local.caddyfile_b64}
CADDYB64
base64 -d /opt/madmallard-platform/caddy/Caddyfile.b64 > /opt/madmallard-platform/caddy/Caddyfile
rm -f /opt/madmallard-platform/caddy/Caddyfile.b64

# server.py is deployed as a normal site artifact from S3.


cat > /etc/systemd/system/madmallard-app.service <<'SERVICE'
[Unit]
Description=Mad Mallard Platform app container
After=docker.service
Requires=docker.service

[Service]
Restart=always
ExecStartPre=-/usr/bin/docker rm -f madmallard-app
ExecStart=/usr/bin/docker run --name madmallard-app --pull=always \
  -e MADMALLARD_PRIMARY_DOMAIN='${var.primary_domain}' \
  -e MADMALLARD_ADMIN_TOKEN='${var.admin_token}' \
  -e MADMALLARD_ADMIN_USERNAME='${var.admin_username}' \
  -e MADMALLARD_ADMIN_PASSWORD_HASH='${var.admin_password_hash}' \
  -e MADMALLARD_ADMIN_SESSION_SECRET='${var.admin_session_secret}' \
  -e MADMALLARD_ENABLE_EMAIL='${var.enable_email_notifications}' \
  -e MADMALLARD_NOTIFY_FROM='${var.notify_email_from}' \
  -e MADMALLARD_NOTIFY_TO='${var.notify_email_to}' \
  -e AWS_REGION='${data.aws_region.current.name}' \
  -v /opt/madmallard-platform/app:/app:ro \
  -v /opt/madmallard-platform/data:/data \
  -p 8000:8000 \
  python:3.12-slim sh -c "if [ '${var.enable_email_notifications}' = 'true' ]; then python -m pip install --no-cache-dir boto3; fi; python /app/server.py"
ExecStop=/usr/bin/docker stop madmallard-app
ExecStopPost=-/usr/bin/docker rm -f madmallard-app

[Install]
WantedBy=multi-user.target
SERVICE

cat > /etc/systemd/system/madmallard-caddy.service <<'SERVICE'
[Unit]
Description=Mad Mallard Platform Caddy container
After=docker.service madmallard-app.service
Requires=docker.service

[Service]
Restart=always
ExecStartPre=-/usr/bin/docker rm -f madmallard-caddy
ExecStart=/usr/bin/docker run --name madmallard-caddy --pull=always \
  --add-host=host.docker.internal:host-gateway \
  -p 80:80 -p 443:443 -p 443:443/udp \
  -v /opt/madmallard-platform/caddy/Caddyfile:/etc/caddy/Caddyfile:ro \
  -v /opt/madmallard-platform/caddy/data:/data \
  -v /opt/madmallard-platform/caddy/config:/config \
  caddy:2-alpine
ExecStop=/usr/bin/docker stop madmallard-caddy
ExecStopPost=-/usr/bin/docker rm -f madmallard-caddy

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable madmallard-app.service madmallard-caddy.service
systemctl restart madmallard-app.service
systemctl restart madmallard-caddy.service

echo "[$(date -Is)] Mad Mallard app deployment complete"
SCRIPT
}

resource "aws_s3_bucket" "artifacts" {
  bucket        = local.artifact_bucket_name
  force_destroy = true
  tags          = var.tags
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_object" "site_files" {
  for_each = {
    for file in local.site_files : file => file
    if !startswith(basename(file), ".")
  }

  bucket       = aws_s3_bucket.artifacts.id
  key          = "${local.artifact_prefix}/${each.value}"
  source       = "${var.site_source_dir}/${each.value}"
  source_hash  = filesha256("${var.site_source_dir}/${each.value}")
  content_type = lookup({
    html = "text/html; charset=utf-8"
    css  = "text/css; charset=utf-8"
    js   = "application/javascript; charset=utf-8"
    png  = "image/png"
    jpg  = "image/jpeg"
    jpeg = "image/jpeg"
    svg  = "image/svg+xml"
    ico  = "image/x-icon"
    webp = "image/webp"
  }, lower(regex("[^.]+$", each.value)), "application/octet-stream")
}

resource "aws_iam_role_policy" "read_artifacts" {
  name = "${var.project_name}-read-site-artifacts"
  role = var.instance_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = aws_s3_bucket.artifacts.arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject"
        ]
        Resource = "${aws_s3_bucket.artifacts.arn}/${local.artifact_prefix}/*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "send_email" {
  count = var.enable_email_notifications ? 1 : 0
  name  = "${var.project_name}-send-ses-email"
  role  = var.instance_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = var.ses_identity_arn != "" ? var.ses_identity_arn : "*"
      }
    ]
  })
}

resource "aws_ssm_document" "app_deploy" {
  name            = "${var.project_name}-app-deploy"
  document_type   = "Command"
  document_format = "JSON"

  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Deploy the Mad Mallard Platform app/site files and Caddy configuration."
    mainSteps = [
      {
        action = "aws:runShellScript"
        name   = "deployApp"
        inputs = {
          timeoutSeconds = "900"
          runCommand     = [local.deploy_script]
        }
      }
    ]
  })

  tags = var.tags
}

resource "aws_ssm_association" "app_deploy" {
  name             = aws_ssm_document.app_deploy.name
  association_name = "${var.project_name}-app-deploy-${substr(local.deploy_hash, 0, 8)}"
  document_version = "$LATEST"

  targets {
    key    = "tag:${var.target_tag_key}"
    values = [var.target_tag_value]
  }

  apply_only_at_cron_interval = false

  depends_on = [
    aws_s3_object.site_files,
    aws_iam_role_policy.read_artifacts,
    aws_iam_role_policy.send_email
  ]
}
