#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE_ARGS=()
if [[ -n "${AWS_PROFILE:-}" ]]; then
  AWS_PROFILE_ARGS=(--profile "$AWS_PROFILE")
fi

PARAM_PREFIX="${PARAM_PREFIX:-/madmallard-platform/prod/admin}"
USERNAME_PARAM="${USERNAME_PARAM:-${PARAM_PREFIX}/username}"
PASSWORD_PARAM="${PASSWORD_PARAM:-${PARAM_PREFIX}/password_hash}"
SESSION_PARAM="${SESSION_PARAM:-${PARAM_PREFIX}/session_secret}"
TOKEN_PARAM="${TOKEN_PARAM:-${PARAM_PREFIX}/token}"

read -r -p "Admin username [greg]: " ADMIN_USERNAME
ADMIN_USERNAME="${ADMIN_USERNAME:-greg}"

read -r -s -p "Admin password: " ADMIN_PASSWORD
echo
read -r -s -p "Confirm admin password: " ADMIN_PASSWORD_CONFIRM
echo

if [[ -z "$ADMIN_PASSWORD" ]]; then
  echo "Password cannot be empty." >&2
  exit 1
fi
if [[ "$ADMIN_PASSWORD" != "$ADMIN_PASSWORD_CONFIRM" ]]; then
  echo "Passwords do not match." >&2
  exit 1
fi

readarray -t GENERATED < <(ADMIN_PASSWORD="$ADMIN_PASSWORD" python3 <<'PY'
import hashlib
import os
import secrets

password = os.environ["ADMIN_PASSWORD"].encode("utf-8")
iterations = 390000
salt = secrets.token_hex(16)
digest = hashlib.pbkdf2_hmac("sha256", password, salt.encode("utf-8"), iterations).hex()
print(f"pbkdf2_sha256${iterations}${salt}${digest}")
print(secrets.token_urlsafe(48))
print(secrets.token_urlsafe(32))
PY
)

PASSWORD_HASH="${GENERATED[0]}"
SESSION_SECRET="${GENERATED[1]}"
EMERGENCY_TOKEN="${GENERATED[2]}"

put_parameter() {
  local name="$1"
  local type="$2"
  local value="$3"
  aws "${AWS_PROFILE_ARGS[@]}" --region "$AWS_REGION" ssm put-parameter \
    --name "$name" \
    --type "$type" \
    --value "$value" \
    --overwrite >/dev/null
  printf 'Updated %s\n' "$name"
}

put_parameter "$USERNAME_PARAM" String "$ADMIN_USERNAME"
put_parameter "$PASSWORD_PARAM" SecureString "$PASSWORD_HASH"
put_parameter "$SESSION_PARAM" SecureString "$SESSION_SECRET"
put_parameter "$TOKEN_PARAM" SecureString "$EMERGENCY_TOKEN"

echo
echo "Admin credentials are now stored in SSM Parameter Store."
echo "Run Terraform apply to redeploy the app configuration, or trigger the app-deploy SSM association once."
