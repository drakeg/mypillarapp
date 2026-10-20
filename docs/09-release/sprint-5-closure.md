# Sprint 5 Closure Record

- Sprint: Sprint 5 — Customer Portal
- Status: Closed at repository/CI level
- Sprint 5 repository/CI release candidate: `474fa941cca5f092d748479aeeef8e90bafdbc4c`
- Sprint 5 implementation candidate before closure gate: `63bcc2850d86661008e2e4f45cbc1302998de881`
- Pre-Sprint-5 rollback baseline: `9f18418dcde6dcb4b1f6c40e1d071baeed6515c3`
- Sprint 5 activation PR: #55
- Sprint 5 implementation PRs: #56, #57, #58, #59, #60, #61, #62, #63, #66, #67
- Maintenance PRs included in the pre-closure baseline: #64, #65
- Post-closure maintenance PRs included in the final release candidate: #68, #69, #72
- Closure gate: S5-T11 / PR #71

## Objective

Provide a tenant-safe Customer Portal for ongoing service delivery through projects, tickets, file references, notifications, richer messaging, unified history, customer-facing portal surfaces, staff authorization, and non-destructive compatibility with existing customer history.

## Delivered scope and acceptance mapping

| Task | Delivered behavior | Primary regression evidence |
| --- | --- | --- |
| S5-T01 | Canonical portal tenant/customer boundary and legacy-history audit | `test_sprint5_portal_tenancy.py` |
| S5-T02 | Tenant-owned customer service projects with CRM linkage and lifecycle | `test_sprint5_portal_projects.py` |
| S5-T03 | Tenant-owned tickets/work requests with customer/internal visibility | `test_sprint5_portal_tickets.py` |
| S5-T04 | Authorization-safe portal file metadata and source validation | `test_sprint5_portal_files.py` |
| S5-T05 | Customer notification preferences and append-oriented delivery history | `test_sprint5_portal_notifications.py` |
| S5-T06 | Non-destructive richer portal messaging with internal-message protection | `test_sprint5_portal_messaging.py` |
| S5-T07 | Unified bounded customer service-history aggregation | `test_sprint5_portal_history.py` |
| S5-T08 | Reusable customer/staff portal authorization and staff operations facade | `test_sprint5_portal_auth.py` |
| S5-T09 | Authenticated customer portal dashboard/detail surfaces and portal reply path | `test_sprint5_portal_views.py` |
| S5-T10 | Audit-gated, additive, idempotent compatibility migration for existing history | `test_sprint5_portal_compat_migration.py` |
| S5-T11 | Focused Sprint 5 CI gate plus formal release/rollback evidence | `make test-sprint5` in GitHub Actions |

The complete `make test` suite remains the protected application regression gate. `make test-sprint2`, `make test-sprint3`, and `make test-sprint4` remain protected focused baseline gates.

## Repository and CI evidence before closure gate

Pre-closure baseline `63bcc2850d86661008e2e4f45cbc1302998de881` passed:

- application `smoke`: success — Actions run `39100849832`, job `117596632486`;
- Terraform `validate`: success — Actions run `39100849835`, job `117596632576`;
- dependency graph update: success — Actions run `39100853979`, job `117596648833`.

The #67 Sprint 5 implementation merge commit `0067d92151c60a71decdf5e164eab81388108448` independently passed:

- application `smoke`: success — Actions run `39100814420`, job `117596527003`;
- Terraform `validate`: success — Actions run `39100814441`, job `117596527217`.

S5-T11 strengthens the application workflow so it explicitly runs:

1. Django `python manage.py check`;
2. `make test` — complete application regression suite;
3. `make test-sprint2` — protected Sprint 2 tenant baseline;
4. `make test-sprint3` — protected Sprint 3 Site Builder baseline;
5. `make test-sprint4` — protected Sprint 4 CRM baseline;
6. `make test-sprint5` — focused Customer Portal regression suite;
7. application container build;
8. non-root runtime-home verification;
9. Docker Compose `.env` host-port resolution verification.

`474fa941cca5f092d748479aeeef8e90bafdbc4c` is the final Sprint 5 repository/CI release candidate. It includes the merged S5-T11 closure gate plus post-closure maintenance updates for Python and GitHub Actions. Its required checks passed:

- application `smoke`: success — Actions run `39357887283`, job `118416845869`;
- Terraform `validate`: success — Actions run `39357887370`, job `118416846243`.

The S5-T11 merge commit `a7766639481fdd5532319aaa605fb6811531ddcd` independently passed:

- application `smoke`: success — Actions run `39357550823`, job `118415749125`;
- Terraform `validate`: success — Actions run `39357550824`, job `118415749265`.

CI success must not be represented as production verification.

## Compatibility decisions

Sprint 5 keeps several boundaries intentionally explicit:

- existing customer dashboard, request history, conversation history, account/profile/auth flows remain protected compatibility routes;
- the new `/portal` surface is additive rather than a destructive route cutover;
- existing conversation/project-request rows remain authoritative and are never rewritten by portal compatibility migration;
- unmatched or ambiguous historical customer identity remains on the legacy compatibility path instead of being guessed;
- customer-visible/internal-only distinctions are enforced in portal tickets, files, and messages;
- managed storage keys are never exposed directly to customer HTML;
- customer message replies use the portal-specific, revalidated customer-scope mutation path;
- bootstrap/platform-admin identity does not implicitly grant tenant portal mutation rights.

## Rollback

The protected repository/CI baseline before Sprint 5 implementation is the Sprint 4 release candidate:

`9f18418dcde6dcb4b1f6c40e1d071baeed6515c3`

If Sprint 5 application behavior must be rolled back:

1. preserve the current SQLite database before rollback;
2. stop portal project/ticket/file/notification writes and compatibility migration runs during the rollback window;
3. restore a compatible known-good application revision;
4. do not delete portal, conversation, CRM, or customer history rows as part of application rollback;
5. verify protected customer login/profile/dashboard/request/conversation journeys first;
6. verify tenant/customer isolation and membership authorization before returning to normal operation;
7. do not blindly apply older Terraform state.

Prefer reverting application code or disabling the additive `/portal` surface over destructive database rollback.

## Production/deployment status

No production deployment or post-deployment Sprint 5 manual smoke test is recorded by this repository closure gate.

Deployment-time evidence still includes:

- authenticated customer access to `/portal` through the deployed hostname/proxy path;
- customer-only visibility for projects, tickets, files, notifications, and messages;
- real deployed denial for foreign customer and cross-tenant record identifiers;
- portal reply behavior through the deployed request/session stack;
- staff portal operations through deployed tenant membership sessions;
- explicit compatibility migration execution, if chosen, after reviewing the audit;
- continued health of legacy dashboard/request/conversation/profile/auth routes after deploying Sprint 5-capable code.

CI success must not be represented as production verification.

## Known limitations and deferred scope

The following remain outside Sprint 5:

- invoice/payment/subscription processing;
- creator storefront/affiliate commerce;
- AI-assisted portal workflows;
- generalized binary-storage-provider implementation;
- destructive customer-history cleanup;
- automatic compatibility migration;
- complete replacement of the legacy customer dashboard/history routes;
- richer staff/admin HTML surfaces beyond the authorization/operations foundation.

## Exit decision

Sprint 5 repository implementation and CI acceptance criteria are satisfied at `474fa941cca5f092d748479aeeef8e90bafdbc4c`.

Production deployment/manual smoke evidence remains intentionally outstanding and must not be inferred from repository closure.
