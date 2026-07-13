#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
patch_path="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sprint1-customer-dashboard-profile.patch"

git apply --check "$patch_path"
git apply "$patch_path"
python3 -m py_compile site/solutions/server.py site/solutions/tenant_auth.py
git diff --check
git status --short
