# AWS Architecture

## Current topology

```mermaid
flowchart TD
    Internet --> SG["Security Group"]
    SG --> EC2["EC2 instance"]
    EC2 --> Caddy["Caddy container :80/:443"]
    Caddy --> App["Application container"]
    App --> EBS["Persistent EBS data"]
    App --> SES
    EC2 --> SSM
    Terraform --> AWS
    Terraform --> State["S3 remote state"]
```

## Services

- EC2 — application host.
- EBS — host/container persistent data.
- S3 — Terraform state and deployment artifacts.
- SES — transactional email.
- SSM Parameter Store — bootstrap admin secrets.
- IAM — EC2 and deployment permissions.
- VPC/security groups — network boundary.
- CloudWatch/SSM execution history — available operational evidence.

## Cost position

The design intentionally avoids RDS, NAT Gateway, Route 53, load balancers, and Elastic IP where not yet justified.

## Growth triggers

Adopt managed database, load balancing, multi-instance application, or enhanced monitoring only when reliability, concurrency, or customer commitments justify the expense.
