# Backup and Recovery

## Protected assets

- Git repository;
- Terraform remote state;
- SSM parameter values;
- SQLite database;
- uploaded files;
- deployment artifacts;
- release tags and documentation.

## Required controls

- encrypted scheduled database backup to S3 before external production use;
- retention policy;
- restore rehearsal;
- state-bucket versioning;
- restricted state access;
- secret recovery/rotation process.

## Recovery order

1. Confirm incident scope.
2. Preserve current data and logs.
3. Restore infrastructure from Terraform.
4. Restore SSM secrets.
5. Deploy tagged application source.
6. Restore database/uploads.
7. verify HTTPS, public forms, customer login, admin login, messaging, and SES.
8. Record recovery evidence.
