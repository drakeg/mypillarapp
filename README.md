# Mad Mallard Platform

<!-- madmallard-badges:start -->
[![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)](https://www.python.org/) [![Django](https://img.shields.io/badge/Django-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/) [![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/) [![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/) [![Docker Compose](https://img.shields.io/badge/Docker%20Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/) [![Terraform](https://img.shields.io/badge/Terraform-844FBA?logo=terraform&logoColor=white)](https://www.terraform.io/) [![AWS](https://img.shields.io/badge/AWS-232F3E?logo=amazonwebservices&logoColor=white)](https://aws.amazon.com/)

[![django](https://github.com/drakeg/mypillarapp/actions/workflows/django.yml/badge.svg)](https://github.com/drakeg/mypillarapp/actions/workflows/django.yml) [![terraform](https://github.com/drakeg/mypillarapp/actions/workflows/terraform.yml/badge.svg)](https://github.com/drakeg/mypillarapp/actions/workflows/terraform.yml) [![License](https://img.shields.io/github/license/drakeg/mypillarapp)](https://github.com/drakeg/mypillarapp/blob/HEAD/LICENSE) [![Issues](https://img.shields.io/github/issues/drakeg/mypillarapp)](https://github.com/drakeg/mypillarapp/issues) [![Pull requests](https://img.shields.io/github/issues-pr/drakeg/mypillarapp)](https://github.com/drakeg/mypillarapp/pulls)
<!-- madmallard-badges:end -->

Mad Mallard Platform is a low-cost, self-hosted business operating platform incubated by Mad Mallard Solutions. The product begins as a practical platform for Mad Mallard Solutions and is intentionally designed to evolve into a multi-tenant SaaS product serving additional businesses.

## Current status

Sprint 8 — Billing and Commercialization is complete at the repository/CI level. Sprints 1–8 are protected compatibility baselines, including tenant-safe plans, subscriptions, Stripe boundaries, invoices, quotas, billing administration, and operational recovery controls.

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

Docker Compose runs the real Mad Mallard platform server, including the platform dashboard, site registry/editor, CRM, inbox, tenant administration, and public-site runtime.

For a trusted local-network review instance, use:

```dotenv
APP_BIND_ADDRESS=0.0.0.0
APP_PORT=8017
MADMALLARD_ROOT_MODE=admin
MADMALLARD_LOCAL_ADMIN=true
MADMALLARD_ADMIN_COOKIE_SECURE=false
MADMALLARD_PRIMARY_DOMAIN=pillar.madmallards.com
```

Then start it:

```bash
docker compose up -d --build
```

With `MADMALLARD_ROOT_MODE=admin`, opening the root URL redirects to `/admin/sites`. The development-only LAN admin mode accepts only loopback/private client addresses and is disabled by default; do not enable it on an Internet-exposed deployment.

For normal production/public behavior, keep:

```dotenv
MADMALLARD_ROOT_MODE=public
MADMALLARD_LOCAL_ADMIN=false
MADMALLARD_ADMIN_COOKIE_SECURE=true
```

The container listens on port `8000`; `APP_PORT` controls the host-side published port.


## Community and support

GitHub Discussions is the primary place for questions, product ideas, deployment experiences, and broader community conversation:

- [Q&A](https://github.com/drakeg/mypillarapp/discussions/categories/q-a) — setup, configuration, deployment, and usage questions.
- [Ideas](https://github.com/drakeg/mypillarapp/discussions/categories/ideas) — product suggestions and early feature conversations.
- [General Discussions](https://github.com/drakeg/mypillarapp/discussions) — open-ended project and community conversation.
- [Issues](https://github.com/drakeg/mypillarapp/issues) — confirmed defects and actionable implementation work.
- [Support guidance](SUPPORT.md) — what to include when asking for help.

## Sponsor development

If Mad Mallard Platform is useful to you or your business, you can support continued open-source development through [GitHub Sponsors](https://github.com/sponsors/drakeg).

Sponsorship does not influence technical decisions, issue priority, security handling, or the accuracy of project documentation.
