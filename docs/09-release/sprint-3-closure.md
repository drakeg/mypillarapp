# Sprint 3 Closure Record

- Sprint: Sprint 3 — Site Builder
- Status: Closed at repository/CI level
- Sprint 3 repository/CI release candidate: `79549d38741a167198146c601c0fdb32b039dbdb`
- Implementation candidate before closure gate: `d7b20269a1af7d2f8c7df8b05c0edbcec6083c18`
- Pre-Sprint-3 rollback baseline: `ace0e41f62989272f005f896d0468f83d2e29b8b`
- Sprint 3 implementation PRs: #30, #31, #32, #33, #35, #36, #38, #39, #40, #41
- Closure gate: S3-T11 / PR #42

## Objective

Allow each organization to configure one or more distinct public sites while preserving tenant isolation, membership authorization, platform-admin separation, and the protected Solutions customer/admin journeys.

## Delivered scope and acceptance mapping

| Task | Delivered behavior | Primary regression evidence |
| --- | --- | --- |
| S3-T01 | Tenant-owned site records with per-organization slug isolation and archival | `test_sprint3_tenant_sites.py` |
| S3-T02 | Domains associate to explicit same-tenant sites; hostname resolves site safely | focused Sprint 3 domain/site tests |
| S3-T03 | Site-scoped branding/theme with legacy-main inheritance and validation | focused Sprint 3 branding tests |
| S3-T04 | Ordered, visible/hidden site navigation with safe HTTP/root-relative targets | focused Sprint 3 navigation tests |
| S3-T05 | Site-scoped pages with draft/published/archived lifecycle and ordering | `test_sprint3_site_pages.py` |
| S3-T06 | Site-owned services and public-form definitions with tenant isolation | `test_sprint3_services_forms.py` |
| S3-T07 | Site-scoped media metadata/references with safe source validation | `test_sprint3_site_media.py` |
| S3-T08 | Membership-derived Site Builder authorization with tenant isolation | `test_sprint3_site_builder_auth.py` |
| S3-T09 | Hostname-aware rendering of published Site Builder content with escaping | `test_sprint3_public_site_rendering.py` |
| S3-T10 | Idempotent, non-destructive staging of Solutions content as draft Site Builder records | `test_sprint3_solutions_migration.py` |
| S3-T11 | Explicit focused Sprint 3 CI gate plus closure/release/rollback evidence | `make test-sprint3` in GitHub Actions |

The complete `make test` suite remains the protected application regression gate, and `make test-sprint2` remains the focused protected multi-tenant baseline.

## Repository and CI evidence

Before S3-T11, `main` commit `d7b20269a1af7d2f8c7df8b05c0edbcec6083c18` passed both repository workflows:

- application `smoke`: success;
- Terraform `validate`: success.

S3-T11 strengthens the application workflow so it explicitly runs:

1. Django `python manage.py check`;
2. `make test` — complete application regression suite;
3. `make test-sprint2` — protected Sprint 2 tenant baseline;
4. `make test-sprint3` — focused Site Builder regression suite;
5. application container build;
6. non-root runtime-home verification;
7. Docker Compose `.env` host-port resolution verification.

PR #42 merged as `79549d38741a167198146c601c0fdb32b039dbdb` with the updated application `smoke` and Terraform `validate` checks both successful. That merge commit is the Sprint 3 repository/CI release candidate.

## Compatibility decision

The existing Mad Mallard Solutions public homepage remains the live compatibility path.

S3-T10 stages a Site Builder representation of current Solutions content but intentionally does not switch the live Solutions homepage to the generic Site Builder renderer. This preserves:

- the live project-request endpoint and validation;
- async chat and private conversation links;
- account navigation;
- customer authentication/dashboard/profile/history flows;
- bootstrap/platform administration behavior.

This is a deliberate compatibility boundary, not an incomplete migration hidden by CI.

## Solutions cutover gate

A future production cutover of Solutions from the protected static homepage to Site Builder rendering requires all of the following before changing the route:

1. behavior-parity tests for project-request submission;
2. behavior-parity tests for async chat;
3. account-navigation and customer authentication parity;
4. deployed/manual smoke evidence;
5. an explicit release decision;
6. a rollback path to the current static homepage.

Until those conditions are met, the staged Solutions Site Builder records should remain non-authoritative.

## Rollback

The last known `main` baseline immediately before Sprint 3 implementation was:

`ace0e41f62989272f005f896d0468f83d2e29b8b`

If Sprint 3 application behavior must be rolled back:

1. preserve the current SQLite database before rollback;
2. stop Site Builder content/domain/tenant configuration changes during the rollback window;
3. restore a compatible known-good application revision;
4. do not delete tenant, site, domain, membership, page, service, form, media, or conversation data as part of application rollback;
5. verify the protected Solutions homepage, project request, chat, login, dashboard, and admin journeys first;
6. verify tenant/domain isolation before returning to normal operation;
7. do not blindly apply older Terraform state.

Where possible, prefer disabling/unpublishing Site Builder content or reverting application code over destructive data rollback.

## Production/deployment status

No production deployment or post-deployment Sprint 3 manual smoke test is recorded by this repository closure workflow.

The following remain deployment-time evidence:

- configured non-Solutions domains resolve to the expected Site Builder site;
- published content renders correctly through the deployed proxy/hostname path;
- draft/archived content is not publicly reachable;
- owner/admin/staff/viewer Site Builder authorization behaves correctly through deployed administration surfaces;
- unknown hosts and cross-tenant paths remain isolated;
- protected Solutions intake/chat/customer/admin journeys remain healthy after a Sprint 3-capable deployment.

CI success must not be represented as production verification.

## Known limitations and deferred scope

The following are intentionally outside the Sprint 3 closure boundary:

- live Solutions cutover to the generic Site Builder renderer;
- binary media upload/storage;
- generalized Site Builder form-submission persistence;
- richer Site Builder administration UI beyond the authorization foundation;
- CRM expansion;
- creator storefront/commerce;
- AI features;
- billing/subscriptions and Developer API commercialization.

The Site Builder public form renderer currently presents published form definitions without enabling a submission action. Existing Solutions project-request submission remains on the protected legacy endpoint.

## Exit decision

Sprint 3 repository implementation and CI acceptance criteria are satisfied at `79549d38741a167198146c601c0fdb32b039dbdb`.

Production deployment/manual smoke evidence and the separate Solutions cutover gate remain intentionally outstanding and must not be inferred from repository closure.
