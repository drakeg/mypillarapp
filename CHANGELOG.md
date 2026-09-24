# Changelog

All notable changes to the product and its engineering system are recorded here.

The format follows Keep a Changelog principles. Formal releases will use Semantic Versioning.

## Unreleased

### Added

- Docker Compose host binding and published port configuration through a documented `.env.example`.
- Site-scoped page/content records with validated slugs, publication lifecycle, ordering, archival, and cross-site/cross-tenant isolation.
- Ordered site-scoped navigation with visibility controls, safe internal/external targets, archive protection, and cross-tenant/site isolation.
- Site-scoped branding and validated theme presets with inheritance from existing tenant branding and cross-site/cross-tenant isolation.
- Domain-to-site association for Site Builder hosts, including migration of existing domains to each tenant’s main site and cross-tenant assignment protection.
- Sprint 3 Site Builder plan and tenant-owned site persistence foundation with organization-scoped isolation and archival tests.
- Formal Sprint 2 closure record with exact CI evidence, rollback baseline, deployment-status limitations, and Sprint 3 handoff.
- Explicit reusable coding and Sprint governance standards for implementation scope, testing, CI evidence, documentation, and closure.
- GitHub Actions regression gating for both the complete application suite and focused Sprint 2 suite.
- Sprint 2 multi-tenant regression evidence plan and focused `make test-sprint2` verification target.
- Explicit platform super-admin session scope and route guards for tenant lifecycle, managed-site, and platform-settings administration.
- Tenant login and request-context authorization now require active organization memberships and project the effective tenant role from the membership.
- Membership-based tenant authorization foundation with explicit roles, organization memberships, legacy-role migration, cross-tenant membership assignment, and revocation support.
- Tenant administration dashboard with tenant status, domain, branding, user, conversation, and project-request summaries.

- Reversible tenant suspension and archival controls that disable domains and revoke active authentication state while preserving tenant data.
- Atomic tenant onboarding for organization, primary domain, owner account, branding, and verification email creation.
- Tenant-scoped branding configuration with validated names, colors, logos, taglines, and support email.

- Tenant organization creation, metadata updates, active/inactive lifecycle controls, and conflict-safe primary-domain management.
- Customer account email uniqueness and login resolution are now scoped to the active tenant.
- Tenant-specific verification and password-reset links with tenant-scoped reset lookup.

- Customer dashboard, request history, and conversation detail are isolated by the authenticated tenant.
- Public project requests, chats, and visitor replies now persist within the resolved tenant.
- Tenant ownership for conversations with existing records migrated to the Solutions tenant.
- Tenant-scoped conversation lookup, customer history, message writes, and status updates.
- HTTP request handling now enforces active tenant hosts and tenant-scoped customer sessions.
- Tenant-aware request context using `Host` and `X-Forwarded-Host` resolution.
- Customer-session isolation that rejects authentication from a different tenant.
- Request-context regression coverage for proxy hosts, unknown domains, and cross-tenant sessions.
- Sprint 2 tenant persistence for domains and tenant-specific settings.
- Host normalization and active-tenant resolution without cross-tenant fallback.
- Tenant isolation regression coverage for domains and settings.
- Sprint 1 automated regression suite for customer authentication, profile management, session invalidation, dashboard counts, and conversation authorization.
- One-command regression test runner through `make test`.

- Authenticated customer conversation and service-request history pages.
- Customer-owned conversation detail pages with chronological message history.
- Customer conversation authorization by signed-in account email.
- Dashboard links to complete request and conversation history.

- Sprint 1 customer dashboard activity counts and recent activity.
- Customer profile editing.
- Authenticated customer password changes.
- Customer-session invalidation after password changes.

- Complete SDLC documentation baseline.
- Product vision, PRD, roadmap, epics, stories, and sprint plan.
- Architecture, AWS, API, testing, operations, CI/CD, and release documentation.
- Architecture Decision Record set.
- Development workflow and repository governance rules.

### Fixed

- Container runtime now gives the non-root `app` user a real writable home directory, preventing Gunicorn control-socket permission errors against `/nonexistent`.
- Removed the remaining request-handler uses of legacy tenant session resolution so conversation detail and profile refresh stay bound to the resolved tenant membership.
- Closed every tenant-auth SQLite connection when its context exits.

### Current implementation baseline

- Public Mad Mallard Solutions site.
- Contact and service-request intake.
- Async customer conversations and response feedback.
- Customer authentication foundation and dashboard.
- Bootstrap admin dashboard and inbox.
- Terraform-managed AWS deployment.
- S3 remote state, SES, Caddy, Docker, and SSM-backed admin secrets.
