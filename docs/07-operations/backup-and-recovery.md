# Backup and Recovery

## Assets Requiring Protection

- SQLite database
- Uploaded customer or site files
- SSM parameter values
- Terraform state
- Git repository
- Caddy certificate data where useful

## Current Recovery Sources

- GitHub for source and documentation
- S3 for Terraform state and deployment artifacts
- SSM Parameter Store for runtime secrets
- EC2-hosted persistent data for the database

## Required Backup Improvement

Before production customer use, automate encrypted SQLite backups to S3 with retention and restore testing.

## Recovery Order

1. Restore or recreate infrastructure with Terraform.
2. Restore SSM parameters.
3. Restore application artifacts from Git.
4. Restore SQLite and uploaded files.
5. Deploy.
6. Verify HTTPS, customer login, admin login, messaging, and notifications.
