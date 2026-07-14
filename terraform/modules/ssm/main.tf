variable "project_name" {
  type = string
}

variable "security_profile" {
  type    = string
  default = "standard"
}

variable "target_tag_key" {
  type = string
}

variable "target_tag_value" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

locals {
  document_content = jsonencode({
    schemaVersion = "2.2"
    description   = "Apply Mad Mallard Platform EC2 security baseline."
    parameters = {
      SecurityProfile = {
        type          = "String"
        description   = "Security profile to apply."
        default       = var.security_profile
        allowedValues = ["minimal", "standard", "hardened"]
      }
    }
    mainSteps = [
      {
        action = "aws:runShellScript"
        name   = "applySecurityBaseline"
        inputs = {
          timeoutSeconds = "900"
          runCommand = [<<-SCRIPT
#!/usr/bin/env bash
set -euo pipefail
PROFILE="{{ SecurityProfile }}"
LOG=/var/log/madmallard-security-baseline.log
exec > >(tee -a "$LOG") 2>&1

echo "[$(date -Is)] Applying Mad Mallard security baseline: $PROFILE"

if [ -f /etc/os-release ]; then
  . /etc/os-release
else
  echo "Cannot determine OS" >&2
  exit 1
fi
ID_LIKE_SAFE="$${ID_LIKE-}"

install_audit_script() {
  cat > /usr/local/bin/madmallard-audit <<'AUDIT'
#!/usr/bin/env bash
set -euo pipefail
echo "Mad Mallard Platform audit - $(date -Is)"
echo
echo "== OS =="
sed -n '1,8p' /etc/os-release || true
echo
echo "== Listening ports =="
ss -tulpn || true
echo
echo "== App =="
systemctl is-active madmallard-app 2>/dev/null || true
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || true
echo
echo "== Caddy =="
systemctl is-active madmallard-caddy 2>/dev/null || true
journalctl -u madmallard-caddy -n 25 --no-pager 2>/dev/null || true
echo
echo "== Fail2ban =="
systemctl is-active fail2ban 2>/dev/null || true
fail2ban-client status 2>/dev/null || true
echo
echo "== Firewall =="
ufw status verbose 2>/dev/null || firewall-cmd --list-all 2>/dev/null || true
echo
echo "== SSM =="
systemctl is-active amazon-ssm-agent 2>/dev/null || systemctl is-active snap.amazon-ssm-agent.amazon-ssm-agent 2>/dev/null || true
AUDIT
  chmod +x /usr/local/bin/madmallard-audit
}

configure_docker_logs() {
  mkdir -p /etc/docker
  if [ ! -f /etc/docker/daemon.json ]; then
    cat > /etc/docker/daemon.json <<'DOCKERJSON'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "5"
  }
}
DOCKERJSON
    systemctl restart docker 2>/dev/null || true
  fi
}

harden_ssh() {
  mkdir -p /etc/ssh/sshd_config.d
  cat > /etc/ssh/sshd_config.d/99-madmallard-hardening.conf <<'SSHCFG'
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
X11Forwarding no
MaxAuthTries 4
ClientAliveInterval 300
ClientAliveCountMax 2
SSHCFG
  sshd -t 2>/dev/null || true
  systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
}

configure_fail2ban() {
  mkdir -p /etc/fail2ban/jail.d
  cat > /etc/fail2ban/jail.d/madmallard-baseline.local <<'F2B'
[DEFAULT]
bantime = 24h
findtime = 10m
maxretry = 5
backend = systemd

[sshd]
enabled = true
port = ssh
logpath = %(sshd_log)s
F2B
  systemctl enable --now fail2ban || true
  systemctl restart fail2ban || true
}

if [[ "$ID" == "ubuntu" || "$ID_LIKE_SAFE" == *"debian"* ]]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y fail2ban ufw unattended-upgrades apt-listchanges curl ca-certificates logrotate
  systemctl enable --now unattended-upgrades || true
  ufw --force reset
  ufw default deny incoming
  ufw default allow outgoing
  ufw allow 22/tcp
  ufw allow 80/tcp
  ufw allow 443/tcp
  ufw --force enable
elif [[ "$ID" == "amzn" || "$ID" == "fedora" || "$ID_LIKE_SAFE" == *"rhel"* ]]; then
  dnf clean all || true
  rm -rf /var/cache/dnf || true
  dnf makecache --refresh -y || true
  dnf install -y --refresh fail2ban firewalld dnf-automatic ca-certificates logrotate || dnf install -y --refresh --allowerasing fail2ban firewalld dnf-automatic ca-certificates logrotate || true
  systemctl enable --now firewalld || true
  firewall-cmd --permanent --add-service=ssh || true
  firewall-cmd --permanent --add-service=http || true
  firewall-cmd --permanent --add-service=https || true
  firewall-cmd --reload || true
  sed -i 's/^apply_updates.*/apply_updates = yes/' /etc/dnf/automatic.conf 2>/dev/null || true
  systemctl enable --now dnf-automatic.timer || true
else
  echo "Unsupported OS ID=$ID ID_LIKE=$ID_LIKE_SAFE" >&2
  exit 1
fi

install_audit_script
configure_docker_logs
configure_fail2ban

if [[ "$PROFILE" == "standard" || "$PROFILE" == "hardened" ]]; then
  harden_ssh
fi

madmallard-audit || true
echo "[$(date -Is)] Security baseline complete"
SCRIPT
          ]
        }
      }
    ]
  })
}

resource "aws_ssm_document" "security_baseline" {
  name            = "${var.project_name}-security-baseline"
  document_type   = "Command"
  document_format = "JSON"
  content         = local.document_content

  tags = var.tags
}

resource "aws_ssm_association" "security_baseline" {
  name = aws_ssm_document.security_baseline.name

  parameters = {
    SecurityProfile = var.security_profile
  }

  targets {
    key    = "tag:${var.target_tag_key}"
    values = [var.target_tag_value]
  }

  schedule_expression         = "rate(30 minutes)"
  apply_only_at_cron_interval = false

  compliance_severity = "MEDIUM"
}

output "security_baseline_document_name" {
  value = aws_ssm_document.security_baseline.name
}

output "security_baseline_association_id" {
  value = aws_ssm_association.security_baseline.association_id
}
