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


## Sprint 2 multi-tenant rollback

Before deploying a Sprint 2 release candidate:

1. record the current known-good `main` commit or release tag;
2. preserve a database backup before any schema/data migration is exercised in production;
3. verify that the rollback source predates the release candidate but is compatible with the preserved database;
4. if tenant authorization or domain resolution is faulty, stop further tenant changes before redeploying the known-good application revision;
5. after rollback, verify the Solutions tenant/Sprint 1 customer and admin journeys first, then confirm tenant/domain state before restoring normal operation.

Do not delete tenant, membership, domain, or conversation data as part of application rollback.
