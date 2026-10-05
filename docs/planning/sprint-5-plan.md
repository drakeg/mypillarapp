# Sprint 5 Plan — Customer Portal

- Status: Active
- Epic: EP-008 — Customer Portal
- Protected baselines: Sprint 1 Single-Business MVP, Sprint 2 Multi-Tenant Foundation, Sprint 3 Site Builder, Sprint 4 CRM
- Sprint 4 repository/CI baseline: `9f18418dcde6dcb4b1f6c40e1d071baeed6515c3`

## Objective

Provide a tenant-safe customer portal for ongoing service delivery: projects, tickets, file references, notifications, customer history, and richer messaging, while preserving existing customer authentication, conversations, CRM isolation, Site Builder behavior, and platform-administration boundaries.

## Entry criteria

- Sprint 4 is closed at repository/CI level.
- `make test`, `make test-sprint2`, `make test-sprint3`, and `make test-sprint4` are protected regression gates.
- Tenant-scoped customer identity and active-membership authorization are established.
- Existing customer dashboard/history and tenant conversations remain protected compatibility paths until explicitly migrated.

## Locked scope

Sprint 5 covers:
- tenant-owned service projects;
- tenant-owned customer tickets/work requests;
- project/ticket/customer/conversation relationships;
- file/document metadata and safe customer visibility controls;
- portal notifications and notification preferences/history;
- richer customer/admin messaging behavior;
- unified customer service-history views;
- customer-portal authorization and tenant isolation;
- compatibility/migration from existing customer dashboard/history behavior;
- focused Sprint 5 regression and closure evidence.

## Explicit non-scope

- invoice/payment/subscription processing;
- creator storefront or affiliate commerce;
- AI-generated responses or summaries;
- binary-storage-provider redesign unless required for safe portal file delivery;
- destructive migration of existing conversations, CRM, or customer history;
- weakening CRM, Site Builder, customer-session, or platform-super-admin boundaries.

## Task sequence

### S5-T01 — Portal tenant/customer boundary audit
Define the canonical ownership and authorization boundary for portal records and audit existing customer dashboard, request history, conversation history, and any legacy project/ticket helpers.

Acceptance:
- new portal records use canonical organization ownership;
- authenticated customer scope requires an active user, active organization, active membership, and normalized customer email;
- compatibility history reads remain bound to both resolved tenant and customer email;
- foreign-tenant and other-customer conversation tokens fail closed;
- existing protected customer dashboard, requests, conversations, and detail routes remain unchanged;
- the legacy-history audit detects missing customer email and unknown organization slugs before history is treated as portal-safe;
- no project/ticket persistence is introduced in this boundary step;
- audit findings and migration constraints are documented in [S5-T01 Customer Portal Boundary Audit](../09-release/sprint-5-portal-boundary-audit.md).

### S5-T02 — Service projects
Add tenant-owned service projects with customer association, lifecycle, status, summary, dates, and CRM linkage where appropriate.

Acceptance:
- canonical projects store `organization_id` referencing the active tenant;
- project customers are active users with active membership in the same organization, and their normalized email is retained as a compatibility snapshot;
- optional CRM company/contact/opportunity links must remain in the same organization and internally consistent;
- project title is required/bounded and summary is bounded;
- statuses are limited to planned, active, on_hold, completed, canceled, or archived;
- optional start/due dates use ISO `YYYY-MM-DD`, and due date cannot precede start date;
- project reads, customer filters, updates, and archival are organization-scoped;
- archived projects remain stored, are hidden by default, and cannot be modified;
- inactive customers, revoked customer memberships, and inactive/suspended organizations fail closed;
- positive and negative cross-tenant/customer tests cover reads and mutations.

### S5-T03 — Tickets and work requests
Add tenant-owned tickets/work requests that may belong to a project and customer.

Acceptance:
- canonical tickets store `organization_id`, customer identity, and optional project linkage;
- ticket customers must be active users with active membership in the same organization;
- a linked project must belong to the same organization and the same customer;
- archived projects cannot accept new tickets;
- ticket status is limited to open, in_progress, waiting_on_customer, resolved, closed, or archived;
- priority is limited to low, normal, high, or urgent;
- subject is required/bounded and description is bounded;
- visibility is explicitly customer or internal;
- project/customer/status/priority/visibility filters remain organization-scoped and foreign filters fail closed;
- archived tickets remain stored, are hidden by default, and cannot be modified;
- revoked customer membership and inactive/suspended organizations fail closed.

### S5-T04 — Portal file metadata foundation
Add project/ticket/customer file references and visibility metadata without introducing unsafe filesystem paths.

Acceptance:
- file metadata is tenant-owned;
- file references may link to projects/tickets/customers only within the same tenant;
- customer-visible vs internal-only access is explicit;
- source identifiers/URLs/keys are validated and never interpreted as arbitrary local paths;
- binary storage implementation may remain external/deferred, but authorization metadata is complete.

### S5-T05 — Notification preferences and delivery records
Add tenant-scoped customer notification preferences plus append-oriented delivery/history records.

Acceptance:
- preferences are scoped to customer identity and tenant;
- supported notification channels/types are explicitly enumerated;
- delivery records are append-oriented and tenant-owned;
- opt-out/preference behavior is enforced before portal-triggered notification creation;
- no cross-tenant notification lookup or mutation is possible.

### S5-T06 — Richer portal messaging
Extend protected conversation behavior for ongoing service delivery without duplicating conversation history.

Acceptance:
- project/ticket relationships may reference existing tenant conversations safely;
- customer replies remain bound to the correct tenant and authenticated identity;
- internal-only messages remain invisible to customers;
- existing chat/project-request flows remain compatible;
- any richer metadata is additive and non-destructive.

### S5-T07 — Unified customer service history
Provide a tenant-safe aggregation of projects, tickets, conversations, file references, notifications, and relevant service history for the authenticated customer.

Acceptance:
- history aggregation cannot leak records from another tenant or customer;
- ordering is deterministic and bounded;
- customer-visible/internal-only distinctions are honored;
- existing dashboard/history links remain compatible until the new portal surface is authoritative.

### S5-T08 — Portal authorization and staff operations
Add reusable portal authorization for customer self-service and tenant staff administration.

Acceptance:
- customer access is limited to records owned by that authenticated customer within the resolved tenant;
- owner/admin/staff tenant memberships may manage portal service records according to least privilege;
- viewer/platform-admin identities do not gain unintended customer-service mutation rights;
- revoked memberships and inactive tenants fail closed.

### S5-T09 — Customer portal dashboard and detail surfaces
Expose projects, tickets, file references, notifications, history, and messaging through authenticated customer-facing pages.

Acceptance:
- all routes resolve tenant before portal data access;
- customer records are isolated by authenticated identity;
- empty/error states do not disclose foreign record existence;
- existing login/profile/password flows remain protected;
- forms and mutations use the authorization layer rather than direct unscoped helpers.

### S5-T10 — Existing customer-history compatibility migration
Adapt or migrate existing request/conversation/dashboard history into the portal model non-destructively where required.

Acceptance:
- no existing conversation or request history is deleted;
- migration/adaptation is idempotent;
- old customer links remain functional or have an explicit compatibility redirect;
- tenant/customer ownership is preserved;
- owner edits/new portal records are not overwritten on rerun.

### S5-T11 — Sprint 5 regression and closure
Add `make test-sprint5`, enforce the focused CI gate, record rollback evidence, and formally close Sprint 5.

## Testing requirements

- `make test` remains the complete regression gate.
- `make test-sprint2`, `make test-sprint3`, and `make test-sprint4` remain protected focused gates.
- Sprint 5 adds `make test-sprint5`.
- Every tenant/customer-owned read and mutation requires positive and negative isolation coverage.
- Customer-visible/internal-only behavior requires explicit tests.
- Compatibility migration tests must prove idempotence and non-destructive behavior.
- CI success is not production/manual-smoke evidence.

## Exit criteria

1. Projects, tickets, files, notifications, messaging relationships, and service history are tenant-safe.
2. Customers can access only their own records within the resolved tenant.
3. Tenant staff operations follow active-membership least privilege.
4. Existing protected customer/auth/conversation behavior remains compatible.
5. Portal compatibility migration is non-destructive and documented.
6. Full protected regression evidence is green.
7. Release/rollback evidence and known limitations are recorded.
