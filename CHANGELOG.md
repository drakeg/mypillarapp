# II-001 — SSM-backed bootstrap admin secrets

## Purpose
Make the platform/bootstrap admin credentials consistent across deployment systems without storing mutable secrets in `terraform.tfvars` or Terraform state.

## Changed
- `terraform/environments/prod/main.tf`
- `terraform/environments/prod/variables.tf`
- `terraform/environments/prod/outputs.tf`
- `terraform/environments/prod/terraform.tfvars.example`
- `terraform/modules/app_deploy/main.tf`
- `terraform/modules/app_deploy/variables.tf`

## Added
- `scripts/set-admin-parameters.sh`
- `scripts/show-admin-parameter-status.sh`

## Intentionally unchanged
- All admin routes, views, HTML, CSS, and dashboard behavior
- `site/solutions/server.py`
- `site/solutions/platform_core.py`
- Messaging/contact behavior
- EC2, VPC, DNS, Caddy, SES, and security-group architecture

## Migration
1. Overlay this delta onto the current known-good repository.
2. Run `scripts/set-admin-parameters.sh` from any authenticated AWS CLI system.
3. Remove or comment out the mutable admin values in local `terraform.tfvars`. The old variable declarations remain temporarily for compatibility, but they are no longer passed to the app.
4. Run `make tf-plan ENV=prod` and verify the EC2 instance is not being replaced.
5. Run `make tf-apply ENV=prod`.

The password generator emits the existing application's preferred format:
`pbkdf2_sha256$iterations$salt$hex_digest`.
