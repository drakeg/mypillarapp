# Sprint 4 Plan — CRM

- Status: Closed at repository/CI level
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

Acceptance:
- activity rows are tenant-owned and append-only through the model API;
- supported kinds are note, status, email, call, meeting, and system;
- actor and body are required and bounded;
- optional company, contact, opportunity, and task links must belong to the same organization;
- foreign relationship filters fail closed;
- timeline reads are organization-scoped, newest-first, and support entity/kind filtering;
- timeline limits are bounded to prevent unbounded reads;
- inactive/suspended organizations cannot create or read CRM activities.

### S4-T07 — Conversation/intake linkage
Allow existing tenant conversations/project requests to be linked to CRM records without duplicating or moving protected conversation data.

Acceptance:
- links reference the existing tenant conversation token and preserve the conversation kind;
- a conversation may link to optional same-tenant company, contact, and opportunity records;
- foreign conversation tokens and foreign CRM relationships fail closed;
- company/contact/opportunity relationship combinations must remain internally consistent;
- re-linking the same tenant conversation updates one link record rather than creating duplicates;
- listing and relationship filters are organization-scoped;
- unlinking removes only the CRM reference and never deletes or mutates the underlying conversation/messages;
- existing project-request/chat endpoints and tenant conversation ownership remain authoritative and unchanged;
- inactive/suspended organizations cannot manage CRM conversation links.

### S4-T08 — Quote foundations
Add quote/estimate draft records and line-item foundations without payment or invoice behavior.

Acceptance:
- canonical quotes store `organization_id` with optional same-tenant company, contact, and opportunity relationships;
- foreign relationships and internally inconsistent company/contact/opportunity combinations fail closed;
- quote lifecycle is limited to draft, sent, accepted, declined, or archived;
- quotes use validated three-letter currency codes and optional ISO `YYYY-MM-DD` validity dates;
- line items use required descriptions, positive integer quantities, non-negative integer-cent unit prices, and explicit non-negative ordering;
- quote subtotal and line totals are derived deterministically from integer cents rather than floating point;
- only draft quotes accept new line items;
- archived quotes cannot be modified;
- cross-tenant quote reads and line writes do not leak data;
- inactive/suspended organizations cannot use quote foundations;
- no invoice, payment, subscription, tax-engine, or payment-provider behavior is introduced.

### S4-T09 — CRM authorization and administration
Expose CRM management through active organization memberships, preserving platform-super-admin separation and least privilege.

Acceptance:
- CRM access is derived only from active tenant memberships in active organizations;
- owner/admin roles may view, manage, and administer CRM capabilities;
- staff may view and manage CRM records but cannot perform CRM administration;
- viewer membership is read-only;
- revoked memberships and suspended/inactive organizations lose CRM access immediately;
- unknown capabilities fail closed;
- the administration facade enforces authorization before invoking canonical CRM models;
- cross-tenant membership does not grant access to another organization's CRM;
- bootstrap/platform-super-admin identity does not implicitly grant tenant CRM access.

### S4-T10 — Legacy CRM migration/compatibility
Migrate or adapt existing `platform_core.py` CRM rows non-destructively into the canonical tenant-safe model.

Acceptance:
- the S4-T01 legacy audit is a hard precondition and any unknown organization, orphan relationship, or cross-tenant relationship blocks migration before canonical rows are copied;
- migration is additive and never deletes or rewrites legacy company, contact, or lead rows;
- legacy companies map to canonical companies and legacy contacts preserve same-tenant company relationships;
- legacy leads map to canonical opportunities with explicit stage mapping;
- free-form legacy lead value/source/priority data is preserved in migration notes rather than guessed into structured monetary fields;
- legacy-to-canonical IDs are recorded in a dedicated mapping table so repeated runs are idempotent;
- canonical owner edits are never overwritten by subsequent migration runs;
- inactive/suspended legacy organizations cannot be migration targets;
- migration remains an explicit operation and does not auto-run during application startup.

### S4-T11 — Sprint 4 regression and closure
Enforce `make test-sprint4`, record acceptance/rollback evidence, and formally close Sprint 4.

Acceptance:
- Make exposes a focused `test-sprint4` target for all `test_sprint4_*.py` regression modules;
- the application `smoke` workflow explicitly runs full, Sprint 2, Sprint 3, and Sprint 4 suites;
- the closure record maps S4-T01 through S4-T11 to regression evidence;
- the implementation candidate and pre-Sprint-4 rollback baseline are recorded exactly;
- final merge SHA and closure run/job IDs are captured after the closure gate merges;
- CI evidence remains explicitly distinct from production/manual smoke evidence.

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
