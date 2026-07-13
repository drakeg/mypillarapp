# Operations Overview

## Production Components

- AWS EC2 host
- Docker
- Python application container
- Caddy container
- SQLite data volume
- AWS SES
- AWS SSM Parameter Store
- S3 Terraform state and deployment artifacts
- Terraform-managed infrastructure

## Operational Priorities

1. Keep monthly cost near zero where practical.
2. Preserve recoverability.
3. Avoid manual server drift.
4. Keep secrets out of source and Terraform state.
5. Maintain HTTPS and least-privilege access.
6. Record every operational change.
