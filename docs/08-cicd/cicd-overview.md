# CI/CD Overview

## Current Model

Deployment is Terraform-driven and manually initiated from an authenticated workstation.

## Target Model

1. Pull request validation for code changes.
2. Syntax and automated tests.
3. Terraform formatting and validation.
4. Reviewed Terraform plan for infrastructure changes.
5. Merge to `main`.
6. Controlled production deployment.
7. Post-deployment smoke tests.
8. Release tag and notes.

Documentation-only phases may write directly to `main` when explicitly approved.
