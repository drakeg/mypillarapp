#!/usr/bin/env bash
set -euo pipefail
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE_ARGS=()
if [[ -n "${AWS_PROFILE:-}" ]]; then
  AWS_PROFILE_ARGS=(--profile "$AWS_PROFILE")
fi
PARAM_PREFIX="${PARAM_PREFIX:-/madmallard-platform/prod/admin}"
for suffix in username password_hash session_secret token; do
  name="${PARAM_PREFIX}/${suffix}"
  if aws "${AWS_PROFILE_ARGS[@]}" --region "$AWS_REGION" ssm get-parameter --name "$name" >/dev/null 2>&1; then
    printf '%-60s %s\n' "$name" "present"
  else
    printf '%-60s %s\n' "$name" "missing"
  fi
done
