# Sprint 4 Plan — CRM

- Status: Active
- Epic: CRM
- Protected baselines: Sprint 1 Single-Business MVP, Sprint 2 Multi-Tenant Foundation, Sprint 3 Site Builder

## Objective

Provide a tenant-safe CRM for contacts, companies, opportunities, tasks, notes, timelines, and quote foundations without weakening the existing customer, messaging, Site Builder, or platform-admin boundaries.

## Entry criteria

- Sprint 3 is closed at repository/CI level.
- Full application, Sprint 2, and Sprint 3 regression gates are green.
- Tenant membership authorization and organization scoping are established.
- Existing legacy CRM helpers in `platform_core.py` are treated as compatibility code pending migration, not as the target architecture.

## Locked scope

Sprint 4 covers:
- tenant-owned companies;
- tenant-owned contacts;
- opportunities/pipeline;
- CRM tasks;
- notes and activity timeline;
- relationships between contacts, companies, opportunities, and conversations where appropriate;
- quote/estimate foundations only;
- membership-authorized CRM administration;
- migration/compatibility for existing CRM rows;
- focused Sprint 4 regression and closure evidence.

## Explicit non-scope

- project/ticket/file delivery workflows;
- invoicing/payment collection;
- subscriptions/billing;
- creator commerce;
- AI assistance;
- destructive CRM migration;
- weakening Site Builder or platform-super-admin boundaries.

## Task sequence

### S4-T01 — CRM tenant boundary and legacy audit
Define canonical CRM persistence around `auth_organizations`, audit existing `platform_core.py` CRM tables/helpers, and prevent new cross-tenant behavior.

Acceptance:
- new CRM ownership uses canonical active organization IDs, not unconstrained text slugs;
- relationship lookups fail closed on missing or foreign records and unrecognized table names;
- a read-only legacy audit detects unknown organizations, cross-tenant associations, and orphan links;
- legacy CRM data, helpers, and the conversation-derived admin CRM view remain untouched;
- positive/negative tests cover tenant boundaries and the legacy audit;
- audit findings and the non-destructive migration contract are documented in [S4-T01 Legacy CRM Audit](../09-release/sprint-4-crm-legacy-audit.md).

### S4-T02 — Companies
Add tenant-owned company records with lifecycle, validation, search/listing, and isolation.

Acceptance:
- canonical company rows store `organization_id` referencing the tenant organization;
- company reads, updates, listings, search, filters, and archival are organization-scoped;
- company status is limited to prospect, customer, vendor, or archived;
- names are required and bounded; optional websites are limited to http/https;
- search matches name, website, industry, and notes while treating SQL wildcard characters literally;
- archived companies remain stored, are hidden from default listings, and cannot be modified;
- inactive/suspended organizations cannot use the canonical company model;
- identical company names may exist in different tenants without leakage;
- the legacy `crm_companies` table remains untouched for S4-T10 migration.

### S4-T03 — Contacts
Add tenant-owned contacts with optional company association, normalized email/phone fields, lifecycle, and isolation.

Acceptance:
- canonical contact rows store `organization_id` and optional canonical company linkage;
- company relationships must belong to the same organization and foreign-company links fail closed;
- contact reads, updates, listings, search, filters, and archival are organization-scoped;
- names are required/bounded, emails are normalized lowercase, and phones normalize to an optional leading plus with 7–15 digits;
- contact lifecycle is limited to lead, prospect, customer, vendor, or archived;
- archived contacts remain stored, are hidden from default listings, and cannot be modified;
- search covers contact identity/details and company name while treating SQL wildcards literally;
- company filtering cannot be used to probe another tenant;
- inactive/suspended organizations cannot use the canonical contact model;
- the legacy `crm_contacts` table remains untouched for S4-T10 migration.

### S4-T04 — Opportunities
Add tenant-owned opportunities with stage, value, expected close metadata, company/contact links, and pipeline ordering.

Acceptance:
- canonical opportunities store `organization_id` and optional same-tenant company/contact links;
- foreign company/contact links and foreign relationship filters fail closed;
- when both company and a company-bound contact are supplied, the relationship must be consistent;
- stages are limited to new, qualified, proposal, negotiation, won, or lost;
- monetary values are non-negative integer cents with validated three-letter currency codes;
- expected close dates use ISO `YYYY-MM-DD`;
- explicit non-negative pipeline position provides stable ordering within a stage;
- opportunity reads, filters, updates, and archival are organization-scoped;
- archived opportunities remain stored, are hidden by default, and cannot be modified;
- inactive/suspended organizations cannot use the canonical opportunity model.

### S4-T05 — CRM tasks
Add tenant-owned tasks linked optionally to contacts, companies, or opportunities with due date/status/priority.

Acceptance:
- canonical CRM tasks store `organization_id` with optional same-tenant company, contact, and opportunity links;
- foreign relationship links and foreign relationship filters fail closed;
- when linked records carry their own relationships, inconsistent company/contact/opportunity combinations are rejected;
- task statuses are limited to open, in_progress, done, canceled, or archived;
- priorities are limited to low, normal, high, or urgent;
- optional due dates use ISO `YYYY-MM-DD` and dated tasks sort before undated tasks;
- task reads, filters, updates, and archival are organization-scoped;
- archived tasks remain stored, are hidden by default, and cannot be modified;
- inactive/suspended organizations cannot use the canonical CRM task model.

### S4-T06 — Notes and activity timeline
Add append-oriented notes/activity records with actor, timestamp, related CRM entity, and tenant scoping.

### S4-T07 — Conversation/intake linkage
Allow existing tenant conversations/project requests to be linked to CRM records without duplicating or moving protected conversation data.

### S4-T08 — Quote foundations
Add quote/estimate draft records and line-item foundations without payment or invoice behavior.

### S4-T09 — CRM authorization and administration
Expose CRM management through active organization memberships, preserving platform-super-admin separation and least privilege.

### S4-T10 — Legacy CRM migration/compatibility
Migrate or adapt existing `platform_core.py` CRM rows non-destructively into the canonical tenant-safe model.

### S4-T11 — Sprint 4 regression and closure
Enforce `make test-sprint4`, record acceptance/rollback evidence, and formally close Sprint 4.

## Testing requirements

- `make test` remains the complete application regression gate.
- `make test-sprint2` and `make test-sprint3` remain protected focused gates.
- Sprint 4 adds `make test-sprint4`.
- Every tenant-owned CRM mutation/read path requires positive and negative cross-tenant tests.
- Migration tests must prove idempotence and non-destructive compatibility.
- CI success is not production/manual-smoke evidence.

## Exit criteria

1. Companies, contacts, opportunities, tasks, notes/timeline, and quote foundations are tenant-scoped.
2. CRM relationships cannot cross organization boundaries.
3. Active membership roles control CRM administration without granting platform administration.
4. Existing intake/conversation behavior remains protected.
5. Legacy CRM compatibility is documented and non-destructive.
6. Full protected regression evidence is green.
7. Release/rollback evidence and known limitations are recorded.
