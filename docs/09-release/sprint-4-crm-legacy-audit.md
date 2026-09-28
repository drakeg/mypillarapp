# S4-T01 — CRM tenant boundary and legacy audit

## Existing implementation (audit)

`site/solutions/platform_core.py` has legacy `crm_companies`,
`crm_contacts`, and `crm_leads` tables. These use an unvalidated
`organization_slug` text column with a default of `solutions`.
The contact/lead foreign keys reference parent IDs but **do not** enforce
that the parent organization matches the child. Legacy listing and summary
helpers have no tenant filter. Their create helpers accept arbitrary
organization slugs and related record IDs without checking tenant ownership.

The current `/admin/crm` handler in `server.py` is a separate,
conversation-derived view; it does not call these legacy CRM helpers.
It is protected by the existing bootstrap-admin boundary. This step
does not expose the legacy tables through a new HTTP route and does not
change that view.

## Canonical persistence contract

- New Sprint 4 CRM records use `organization_id`, referencing
  `auth_organizations(id)`, not unconstrained organization-slug text.
- Resolve write targets from active organizations; missing/inactive orgs fail
  closed.
- Child records must validate each referenced parent belongs to the **same**
  organization, not merely that its ID exists.
- Queries for CRM records always include the resolved organization ID.
- Do not use platform bootstrap-admin authentication to imply that a tenant
  member may cross organization boundaries.
- Tenant membership authorization is a separate S4-T09 boundary, not a
  replacement for data-layer ownership checks.
- New CRM table names are isolated from the existing `crm_*` legacy
  tables until S4-T10; no in-place destructive conversion occurs here.

`crm_tenancy.organization_id` and `ensure_same_organization`
provide reusable fail-closed checks. The relationship helper only accepts
registered canonical table identifiers, preventing SQL identifier injection.
The canonical tables themselves are introduced in their scoped Sprint 4
feature tasks; S4-T01 does not create empty speculative tables.

## Legacy inspection before S4-T10

`crm_tenancy.audit_legacy_crm()` reads but never creates or mutates the
legacy CRM tables. It counts companies/contacts/leads and reports:

- rows whose organization slug does not match any canonical organization;
- contact/company and lead/contact/company links across organizations;
- references to missing parent rows.

A zero-hazard report is a necessary precondition for straightforward
migration, not proof that the data is complete or that authorization is
correct. S4-T10 must quarantine or explicitly resolve suspect links and
record the decision; it must not silently reassign foreign records.

## Compatibility and rollback

Existing `platform_core.py` CRM data, functions, and
`/admin/crm` behavior are unchanged. There is no schema migration,
domain change, app routing change, or infrastructure change in S4-T01.
Rollback removes only the new module, tests, and documentation.
Full application, Sprint 2 and Sprint 3 regression suites remain protected.
