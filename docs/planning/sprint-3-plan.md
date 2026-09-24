# Sprint 3 Plan — Site Builder

- Status: Active
- Epic: EP-006 — Site Builder
- Protected baselines: Sprint 1 Single-Business MVP and Sprint 2 Multi-Tenant Foundation

## Objective

Allow each organization to configure one or more distinct public sites while preserving tenant isolation, membership authorization, platform-admin separation, and the stable Solutions customer/admin journeys.

## Entry criteria

- Sprint 2 formally closed.
- Full Sprint 1 + Sprint 2 regression suite green.
- Coding and Sprint governance standards documented.
- Tenant organizations, memberships, domains, and request context available.

## Locked scope

Sprint 3 covers:

- tenant-owned site records;
- site branding/theme configuration;
- navigation;
- pages/content structure;
- services and public forms;
- media references/library foundation;
- domain-to-site association;
- tenant-authorized site administration;
- public rendering from resolved site configuration;
- migration/compatibility for the existing Solutions public site;
- Sprint 3 regression and release evidence.

## Explicit non-scope

- CRM expansion;
- projects/tickets/files beyond existing request flows;
- creator storefront/affiliate tools;
- AI features;
- billing/subscriptions;
- destructive tenant migration.

## Task sequence

### S3-T01 — Tenant-owned site persistence

Introduce the real `ORGANIZATION → SITE` persistence boundary.

Acceptance:
- active organizations receive an initial `main` site record;
- one organization may own multiple sites;
- the same site slug may exist in different organizations;
- duplicate slugs within one organization are rejected;
- reads, listings, updates, and archival are organization-scoped;
- archival preserves the record;
- existing public rendering is unchanged;
- full protected regression suite remains green.

### S3-T02 — Domain-to-site association

Attach tenant domains to explicit site records while preserving current hostname resolution and preventing cross-tenant domain assignment.

### S3-T03 — Site branding and theme model

Move Site Builder visual configuration into site-scoped settings with validated theme/brand values.

### S3-T04 — Navigation model

Add ordered, tenant/site-scoped navigation items with safe internal/external links.

### S3-T05 — Page/content model

Add site-scoped pages, slugs, publication status, ordering, and safe content fields.

### S3-T06 — Services and public forms

Represent services and form configuration as site-owned content without breaking existing request intake.

### S3-T07 — Media foundation

Add site-scoped media metadata/references and safe ownership rules. Binary-storage changes require separate cost/deployment review.

### S3-T08 — Tenant-authorized Site Builder administration

Expose Site Builder management through organization membership roles while preserving the separate platform-super-admin boundary.

### S3-T09 — Public site rendering

Resolve and render public site configuration from the hostname/site model with a compatibility path for Mad Mallard Solutions.

### S3-T10 — Existing Solutions migration

Migrate the current Solutions public site into the Site Builder model without changing protected public/customer behavior.

### S3-T11 — Sprint 3 regression and closure

Complete the Site Builder acceptance matrix, release/rollback evidence, and formal Sprint closure.

## Testing requirements

- `make test` remains the complete protected regression gate.
- `make test-sprint2` remains available for the protected multi-tenant baseline.
- `make test-sprint3` runs focused Site Builder tests.
- Tenant/security changes require positive and negative isolation tests.
- CI success must not be represented as production verification.

## Exit criteria

1. Each organization can own independently configurable sites.
2. Domain resolution selects the correct site without cross-tenant leakage.
3. Branding, navigation, pages, services/forms, and media references are site-scoped.
4. Authorized organization roles can administer their sites without gaining platform administration.
5. The existing Solutions public/customer/admin journeys remain compatible.
6. Full Sprint 1–3 regression evidence is green.
7. Release/rollback evidence and known limitations are recorded.
