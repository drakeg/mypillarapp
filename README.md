# Mad Mallard Platform

Mad Mallard Platform is a low-cost, self-hosted business operating platform incubated by Mad Mallard Solutions. The product begins as a practical platform for Mad Mallard Solutions and is intentionally designed to evolve into a multi-tenant SaaS product serving additional businesses.

## Current status

Sprint 1 — Single-Business MVP is the active implementation baseline.

The current system includes:

- public Mad Mallard Solutions site;
- contact and service-request intake;
- async customer messaging;
- optional customer feedback;
- customer registration, login, email verification, password reset, dashboard, and profile;
- a separate bootstrap admin login and admin dashboard;
- Docker/Caddy deployment on AWS EC2;
- Terraform-managed infrastructure;
- S3 remote Terraform state;
- AWS SES notifications;
- AWS Systems Manager Parameter Store for bootstrap admin secrets.

## Start here

1. [Product Vision](docs/product/product-vision.md)
2. [Product Requirements Document](docs/product/product-requirements-document.md)
3. [Approved Roadmap](docs/planning/product-roadmap.md)
4. [Sprint Plan](docs/planning/sprint-plan.md)
5. [Development Workflow](docs/governance/development-workflow.md)
6. [System Architecture](docs/architecture/system-architecture.md)
7. [AWS Architecture](docs/aws/aws-architecture.md)
8. [Test Strategy](docs/testing/test-strategy.md)
9. [Operations Runbook](docs/operations/operations-runbook.md)
10. [ADR Index](docs/adr/README.md)

## Source of truth

The repository is authoritative for product scope, architecture, sprint requirements, acceptance tests, implementation history, operating procedures, and decisions.

## Scope rule

Only the active Sprint step may change implementation. Unrelated cleanup, protected admin changes, and infrastructure changes are prohibited unless explicitly required by that step.
