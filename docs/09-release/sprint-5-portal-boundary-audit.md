# S5-T01 Customer Portal Boundary Audit

## Purpose

Establish the ownership and authorization boundary for Sprint 5 before introducing project, ticket, file, or notification persistence.

## Existing customer-service behavior

The current authenticated customer experience is conversation-backed:

- `/dashboard` summarizes customer activity from tenant-owned conversations;
- `/requests` lists `project_request` conversations for the signed-in customer's tenant and email;
- `/conversations` lists `chat` conversations for the signed-in customer's tenant and email;
- `/account/conversations/<token>` resolves the token inside the current tenant and then verifies that the conversation email matches the signed-in customer's email;
- public project-request and chat creation already resolve the request tenant before writing conversation rows.

There are no canonical Sprint 5 project or ticket tables yet. Existing “requests” are conversation records with `kind='project_request'`, not project entities.

## Canonical portal ownership contract

New Sprint 5 portal records will use:

1. canonical active `auth_organizations.id` ownership;
2. authenticated customer identity derived from an active `auth_users` row plus active membership in the resolved organization;
3. normalized customer email as the compatibility key for existing conversation history until a later explicit migration introduces stronger direct customer identifiers;
4. same-tenant relationships only for future projects, tickets, files, notifications, conversations, and CRM references.

Customer-visible reads must fail closed when either tenant ownership or customer identity does not match.

## Existing compatibility boundary

Existing conversation and request history remains authoritative during early Sprint 5.

S5-T01 does not:

- create project/ticket/file/notification tables;
- rewrite conversation ownership;
- change customer routes;
- change admin routes;
- copy or delete conversation history;
- introduce a new customer identity migration.

## Audit risks

The existing conversation model permits rows with:

- blank customer email;
- an organization slug that does not match a canonical organization.

Those rows cannot safely participate in authenticated customer portal aggregation without explicit handling.

`portal_tenancy.audit_existing_customer_history()` reports:

- total conversations;
- project-request count;
- chat count;
- rows missing customer email;
- rows referencing unknown organizations.

A clean audit requires zero missing-email rows and zero unknown-organization rows before existing conversation history can be treated as a complete authenticated-customer portal source.

## Authorization findings

The current customer request context already resolves tenant before customer routes.

The new portal boundary strengthens the service-layer contract by requiring:

- active user;
- active organization;
- active membership in that organization;
- normalized customer email.

A revoked membership or inactive organization therefore fails before portal service-history access.

Tenant staff/admin authorization remains a separate concern for S5-T08 and must use active tenant membership rather than bootstrap/platform-admin authority.

## Migration implications

Future Sprint 5 persistence should not infer project entities directly from every legacy `project_request` row without an explicit migration rule.

Until S5-T10:

- conversation/project-request history remains in place;
- new portal models may link to existing conversation tokens;
- compatibility aggregation may include qualifying existing conversations;
- no destructive cleanup is permitted.

## Decision

S5-T01 establishes the portal boundary without changing production behavior.

The next implementation step is S5-T02 — tenant-owned service projects.
