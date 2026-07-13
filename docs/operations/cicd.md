# CI/CD

## Current

Deployment is manually initiated from an authenticated workstation through Terraform and SSM-driven application deployment.

## Required pipeline checks

- Python syntax/tests;
- secret scanning;
- Terraform fmt/validate;
- Terraform security scanning;
- changed-file/scope review;
- container build validation;
- smoke tests.

## Production promotion

Production remains explicit until automated promotion is proven safe and rollback is reliable.

## Documentation-only work

May go directly to `main` only when explicitly authorized.
