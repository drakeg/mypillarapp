# Sprint 4 Closure Record

- Sprint: Sprint 4 — CRM
- Status: Closed at repository/CI level
- Sprint 4 repository/CI release candidate: `9f18418dcde6dcb4b1f6c40e1d071baeed6515c3`
- Sprint 4 implementation candidate before closure gate: `179ceac3c45d0a418aa732e23511fcff79267144`
- Pre-Sprint-4 rollback baseline: `79549d38741a167198146c601c0fdb32b039dbdb`
- Sprint 4 implementation PRs: #44, #45, #46, #47, #48, #49, #50, #51, #52, #53
- Closure gate: S4-T11 / PR #54

## Objective

Provide a tenant-safe CRM for companies, contacts, opportunities, tasks, notes/activity, conversation linkage, quote foundations, membership authorization, and non-destructive legacy compatibility without weakening protected customer, messaging, Site Builder, or platform-admin boundaries.

## Delivered scope and acceptance mapping

| Task | Delivered behavior | Primary regression evidence |
| --- | --- | --- |
| S4-T01 | Canonical CRM tenant boundary and read-only legacy integrity audit | `test_sprint4_crm_tenancy.py` |
| S4-T02 | Tenant-owned companies with lifecycle, validation, search, and isolation | `test_sprint4_crm_companies.py` |
| S4-T03 | Tenant-owned contacts with normalized identity fields and same-tenant company links | `test_sprint4_crm_contacts.py` |
| S4-T04 | Tenant-owned opportunities with stage/value/close metadata and ordered pipeline | `test_sprint4_crm_opportunities.py` |
| S4-T05 | Tenant-owned CRM tasks with due/status/priority and relationship consistency | `test_sprint4_crm_tasks.py` |
| S4-T06 | Append-only notes/activity timeline with actor/timestamp and safe entity links | `test_sprint4_crm_activities.py` |
| S4-T07 | Non-destructive linkage from existing tenant conversations/project requests to CRM | `test_sprint4_crm_conversation_links.py` |
| S4-T08 | Quote/estimate foundations with integer-cent line totals and no billing behavior | `test_sprint4_crm_quotes.py` |
| S4-T09 | Membership-based CRM authorization and administration facade | `test_sprint4_crm_auth.py` |
| S4-T10 | Audit-gated, additive, idempotent legacy CRM migration/compatibility | `test_sprint4_crm_legacy_migration.py` |
| S4-T11 | Focused Sprint 4 CI gate plus formal release/rollback evidence | `make test-sprint4` in GitHub Actions |

The complete `make test` suite remains the protected application regression gate. `make test-sprint2` and `make test-sprint3` remain focused protected baseline gates.

## Repository and CI evidence before closure gate

Implementation candidate `179ceac3c45d0a418aa732e23511fcff79267144` passed:

- application `smoke`: success — Actions run `37091874967`, job `111113743157`;
- Terraform `validate`: success — Actions run `37091874971`, job `111113743224`.

S4-T11 strengthens the application workflow so it explicitly runs:

1. Django `python manage.py check`;
2. `make test` — complete application regression suite;
3. `make test-sprint2` — protected Sprint 2 tenant baseline;
4. `make test-sprint3` — protected Sprint 3 Site Builder baseline;
5. `make test-sprint4` — focused CRM regression suite;
6. application container build;
7. non-root runtime-home verification;
8. Docker Compose `.env` host-port resolution verification.

`9f18418dcde6dcb4b1f6c40e1d071baeed6515c3` is the final Sprint 4 repository/CI release candidate. Its closure checks passed:

- application `smoke`: success — Actions run `37093520599`, job `111118672670`;
- Terraform `validate`: success — Actions run `37093520541`, job `111118672538`.

CI success must not be represented as production verification.

## Compatibility decisions

Sprint 4 keeps several boundaries intentionally explicit:

- existing tenant conversation/project-request data remains authoritative; CRM linkage stores references rather than copying message history;
- legacy CRM tables/helpers remain available and are never destructively rewritten by migration;
- legacy lead free-form value/source/priority information is preserved in migration notes rather than guessed into structured fields;
- quote foundations stop before invoices, payments, subscriptions, taxes, or payment-provider integration;
- bootstrap/platform-super-admin identity does not implicitly grant tenant CRM access.

## Rollback

The protected repository/CI baseline before Sprint 4 implementation is Sprint 3 release candidate:

`79549d38741a167198146c601c0fdb32b039dbdb`

If Sprint 4 application behavior must be rolled back:

1. preserve the current SQLite database before rollback;
2. stop CRM writes and legacy migration runs during the rollback window;
3. restore a compatible known-good application revision;
4. do not delete canonical CRM or legacy CRM rows as part of application rollback;
5. verify protected Solutions intake/chat/customer/admin journeys first;
6. verify tenant isolation and membership authorization before returning to normal operation;
7. do not blindly apply older Terraform state.

Prefer reverting application code or disabling CRM surfaces over destructive database rollback.

## Production/deployment status

No production deployment or post-deployment Sprint 4 manual smoke test is recorded by this repository closure gate.

Deployment-time evidence still includes:

- tenant CRM administration through deployed membership-authenticated surfaces;
- cross-tenant denial through real deployed routes;
- conversation/project-request linkage against deployed data;
- explicit legacy migration execution, if chosen, after reviewing the audit;
- protected Solutions intake/chat/customer/admin behavior after deploying Sprint 4-capable code.

CI success must not be represented as production verification.

## Known limitations and deferred scope

The following remain outside Sprint 4:

- richer CRM HTML/UI beyond the administration service foundation;
- invoice/payment/subscription/tax behavior;
- creator commerce;
- AI-assisted CRM;
- destructive legacy CRM cleanup;
- automatic legacy migration;
- live Solutions Site Builder cutover.

## Exit decision

Sprint 4 repository implementation and CI acceptance criteria are satisfied at `9f18418dcde6dcb4b1f6c40e1d071baeed6515c3`.

Production deployment/manual smoke evidence remains intentionally outstanding and must not be inferred from repository closure.
