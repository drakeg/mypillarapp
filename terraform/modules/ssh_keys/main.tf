variable "project_name" {
  type = string
}

variable "ssh_public_keys" {
  description = "SSH public keys to install in authorized_keys on the EC2 instance."
  type        = list(string)
  default     = []
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

locals {
  cleaned_keys = distinct([
    for key in var.ssh_public_keys : trimspace(key)
    if trimspace(key) != ""
  ])

  keys_b64 = base64encode(join("\n", local.cleaned_keys))
}

resource "aws_ssm_document" "ssh_keys" {
  name            = "${var.project_name}-ssh-keys"
  document_type   = "Command"
  document_format = "JSON"

  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Install Mad Mallard Platform managed SSH public keys."
    mainSteps = [
      {
        action = "aws:runShellScript"
        name   = "installSshKeys"
        inputs = {
          timeoutSeconds = "300"
          runCommand = [
            <<-SCRIPT
            #!/usr/bin/env bash
            set -euo pipefail

            LOG=/var/log/madmallard-ssh-keys.log
            exec > >(tee -a "$LOG") 2>&1
            echo "[$(date -Is)] Installing Mad Mallard managed SSH keys"

            KEYS_B64='${local.keys_b64}'
            KEYS_FILE=/tmp/madmallard-authorized-keys
            printf '%s' "$KEYS_B64" | base64 -d > "$KEYS_FILE"

            START_MARKER='# BEGIN MAD MALLARD MANAGED SSH KEYS'
            END_MARKER='# END MAD MALLARD MANAGED SSH KEYS'

            install_for_user() {
              local user="$1"
              local home_dir
              home_dir=$(getent passwd "$user" | cut -d: -f6 || true)

              if [ -z "$home_dir" ] || [ ! -d "$home_dir" ]; then
                return 0
              fi

              local ssh_dir="$home_dir/.ssh"
              local auth_file="$ssh_dir/authorized_keys"

              mkdir -p "$ssh_dir"
              touch "$auth_file"

              awk -v start="$START_MARKER" -v end="$END_MARKER" '
                $0 == start { skip=1; next }
                $0 == end { skip=0; next }
                skip != 1 { print }
              ' "$auth_file" > "$auth_file.tmp"

              mv "$auth_file.tmp" "$auth_file"

              {
                echo "$START_MARKER"
                cat "$KEYS_FILE"
                echo "$END_MARKER"
              } >> "$auth_file"

              chown -R "$user:$user" "$ssh_dir"
              chmod 700 "$ssh_dir"
              chmod 600 "$auth_file"
              echo "Installed managed SSH keys for $user"
            }

            install_for_user ec2-user
            install_for_user ubuntu

            rm -f "$KEYS_FILE"
            echo "[$(date -Is)] SSH key installation complete"
            SCRIPT
          ]
        }
      }
    ]
  })

  tags = var.tags
}

resource "aws_ssm_association" "ssh_keys" {
  count = length(local.cleaned_keys) > 0 ? 1 : 0

  name = aws_ssm_document.ssh_keys.name

  targets {
    key    = "tag:${var.target_tag_key}"
    values = [var.target_tag_value]
  }

  apply_only_at_cron_interval = false
  schedule_expression         = "rate(30 minutes)"

  depends_on = [aws_ssm_document.ssh_keys]
}

output "document_name" {
  value = aws_ssm_document.ssh_keys.name
}

output "association_id" {
  value = length(aws_ssm_association.ssh_keys) > 0 ? aws_ssm_association.ssh_keys[0].association_id : ""
}

output "managed_key_count" {
  value = length(local.cleaned_keys)
}
