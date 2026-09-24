# Mad Mallard Platform

Mad Mallard Platform is a low-cost, self-hosted business operating platform incubated by Mad Mallard Solutions. The product begins as a practical platform for Mad Mallard Solutions and is intentionally designed to evolve into a multi-tenant SaaS product serving additional businesses.

## Current status

Sprint 3 — Site Builder is the active planning/implementation baseline. Sprint 2 — Multi-Tenant Foundation is complete and protected alongside the Sprint 1 compatibility baseline.

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
- AWS Systems Manager Parameter Store for bootstrap admin secrets;
- tenant domain resolution and request isolation;
- tenant-scoped customer identity, conversations, and authentication links;
- tenant organization, branding, onboarding, lifecycle, and administration services;
- membership-based tenant RBAC and authorization;
- a separate platform-super-admin boundary;
- enforced Sprint 1 + Sprint 2 regression gates.

## Start here

1. [Product Vision](docs/product/product-vision.md)
2. [Product Requirements Document](docs/product/product-requirements-document.md)
3. [Approved Roadmap](docs/planning/product-roadmap.md)
4. [Sprint Plan](docs/planning/sprint-plan.md)
5. [Development Workflow](docs/governance/development-workflow.md)
6. [Coding Standards](docs/governance/coding-standards.md)
7. [Sprint Standards](docs/governance/sprint-standards.md)
8. [System Architecture](docs/architecture/system-architecture.md)
9. [AWS Architecture](docs/aws/aws-architecture.md)
10. [Test Strategy](docs/testing/test-strategy.md)
11. [Operations Runbook](docs/operations/operations-runbook.md)
12. [ADR Index](docs/adr/README.md)

## Source of truth

The repository is authoritative for product scope, architecture, sprint requirements, acceptance tests, implementation history, operating procedures, and decisions.

## Scope rule

Only the active Sprint step may change implementation. Unrelated cleanup, protected admin changes, and infrastructure changes are prohibited unless explicitly required by that step.


## Local Docker Compose

Copy the example environment file and choose the host port you want to publish:

```bash
cp .env.example .env
```

Example `.env`:

```dotenv
APP_BIND_ADDRESS=127.0.0.1
APP_PORT=8080
```

Then start the stack:

```bash
docker compose up --build
```

The application still listens on port `8000` inside the container; `APP_PORT` controls only the host-side published port. With the example above, open `http://127.0.0.1:8080`.
