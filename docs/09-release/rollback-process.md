# Rollback Process

## Application Rollback

1. Identify the last known-good tag or commit.
2. Restore source to that release.
3. Redeploy through the standard Terraform/application deployment process.
4. Run smoke and regression tests.

## Infrastructure Rollback

Do not blindly apply an old Terraform state. Review the current state and desired configuration. Restore through a deliberate Terraform change.

## Data Rollback

Restore from a verified backup only after preserving the current database and confirming the recovery point.
