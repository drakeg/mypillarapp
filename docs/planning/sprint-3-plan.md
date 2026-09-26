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

Acceptance:
- existing domains migrate to each organization’s `main` site;
- domain registration defaults to `main` but may target another non-archived site in the same organization;
- a domain cannot be reassigned to a different organization;
- a domain cannot target a site owned by another organization;
- archived sites cannot receive new domains and do not resolve as public sites;
- the existing `resolve_tenant(host)` contract remains compatible.

### S3-T03 — Site branding and theme model

Move Site Builder visual configuration into site-scoped settings with validated theme/brand values.

Acceptance:
- branding is stored per site rather than only per organization;
- each `main` site inherits existing Sprint 2 tenant branding until a Site Builder override is saved;
- secondary sites default to their own site name and standard brand defaults;
- same-tenant sites and same-slug cross-tenant sites remain isolated;
- themes are restricted to approved presets;
- colors, logo URLs, and support email values are validated;
- archived or cross-tenant sites cannot be updated;
- saving Site Builder branding does not mutate the legacy tenant-branding record.

### S3-T04 — Navigation model

Add ordered, tenant/site-scoped navigation items with safe internal/external links.

Acceptance:
- navigation items belong to exactly one site;
- items are ordered by explicit non-negative position with stable insertion-order tie breaking;
- visibility can be toggled without deleting the item;
- internal root-relative links are allowed;
- external links are restricted to http/https;
- protocol-relative, javascript, and unsupported-scheme targets are rejected;
- reads, updates, and deletes cannot cross site or organization boundaries;
- archived sites cannot be modified.

### S3-T05 — Page/content model

Add site-scoped pages, slugs, publication status, ordering, and safe content fields.

Acceptance:
- each page belongs to exactly one site;
- page slugs are unique within a site but may repeat across different sites;
- page states are limited to draft, published, and archived;
- page listings are ordered by explicit non-negative position with stable insertion-order tie breaking;
- public-style listings can return published pages only;
- archived pages remain stored but are hidden from default listings and cannot be modified;
- archived sites cannot receive or modify pages;
- reads and updates cannot cross site or organization boundaries;
- page content is stored as data and is not interpreted as executable markup by this model layer.

### S3-T06 — Services and public forms

Represent services and form configuration as site-owned content without breaking existing request intake.

Acceptance:
- services are site-owned, ordered, and support draft/published/archived lifecycle;
- service slugs are unique within a site but may repeat across sites;
- public forms are site-owned and support draft/published/archived lifecycle;
- form fields are validated against an approved field-type set and unique field names;
- select fields require unique non-empty options;
- services/forms cannot be read or updated across tenant/site boundaries;
- archived services/forms/sites cannot be modified;
- the existing static project-request configuration and live intake endpoints remain unchanged until the later rendering/migration steps.

### S3-T07 — Media foundation

Add site-scoped media metadata/references and safe ownership rules. Binary-storage changes require separate cost/deployment review.

Acceptance:
- media references belong to exactly one site;
- slugs are unique within a site but may repeat across sites;
- supported kinds are image, video, audio, and document;
- sources are limited to root-relative paths or http/https URLs;
- protocol-relative and unsupported-scheme sources are rejected;
- optional MIME metadata uses type/subtype format;
- media supports draft/published/archived lifecycle and published/kind filtering;
- reads and updates cannot cross site or organization boundaries;
- archived media and archived sites cannot be modified;
- this step stores metadata/references only and introduces no binary upload/storage backend or paid infrastructure.

### S3-T08 — Tenant-authorized Site Builder administration

Expose Site Builder management through organization membership roles while preserving the separate platform-super-admin boundary.

Acceptance:
- Site Builder authorization is derived only from active organization memberships;
- owner and admin roles may administer site settings, domains, and all Site Builder content;
- staff may administer branding, navigation, pages, services, forms, and media but not site lifecycle/settings or domains;
- viewer has no Site Builder administration access;
- authorization never crosses organization boundaries;
- revoked memberships immediately lose Site Builder access;
- archived sites cannot be administered;
- unknown capabilities fail closed;
- tenant Site Builder roles do not grant or imply platform-super-admin access.

### S3-T09 — Public site rendering

Resolve and render public site configuration from the hostname/site model with a compatibility path for Mad Mallard Solutions.

Acceptance:
- public rendering resolves the target Site Builder site from the request hostname;
- only published sites render Site Builder content publicly;
- published pages, services, forms, and visible navigation are rendered from the resolved site only;
- draft and archived content is not exposed publicly;
- page content is HTML-escaped rather than interpreted as executable markup;
- unknown Site Builder paths return 404 instead of falling through to another tenant/site;
- public form definitions render without enabling submission behavior until the later migration step;
- the existing Solutions main site remains on the protected static compatibility path until S3-T10.

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
