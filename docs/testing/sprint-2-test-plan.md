# Sprint 2 Test Plan

## Purpose

Sprint 2 establishes the multi-tenant foundation while preserving the Sprint 1 single-business baseline. This plan is the release evidence matrix for tenant resolution, tenant-scoped data, tenant lifecycle, organization memberships, authorization boundaries, and compatibility.

## Automated commands

- `make test-sprint2` runs all `tests/test_sprint2_*.py` regression modules.
- `make test` runs the complete Sprint 1 + Sprint 2 regression suite and is executed by the GitHub Actions smoke job.
- `make test-sprint2` is also executed by the smoke job as an explicit Sprint 2 evidence gate.
- Terraform validation remains required through the existing GitHub Actions validate job.

## Acceptance matrix

| Area | Required evidence | Expected result |
|---|---|---|
| Tenant resolution | domain/host and forwarded-host tests | configured active host resolves only its tenant; unknown host is rejected |
| Request context | request-context and server-context tests | tenant comes from trusted host context; sessions cannot cross tenants without membership |
| Conversations | tenant conversation/server tests | reads, writes, history, replies, and status operations remain tenant-scoped |
| Customer activity | dashboard/history isolation tests | customers see only activity for the resolved tenant |
| Auth links | verification/reset link tests | links use tenant host and tenant-scoped account lookup |
| User identities | tenant identity tests | same email may exist in separate tenant identities without incorrect login resolution |
| Organizations/domains | organization and context tests | lifecycle/domain changes remain conflict-safe and tenant-specific |
| Branding/configuration | tenant branding tests | tenant settings remain isolated and validated |
| Onboarding | onboarding tests | organization, domain, owner membership, branding, and verification state are created atomically |
| Lifecycle | lifecycle tests | suspend/archive disables tenant access and active sessions without deleting tenant data |
| Admin dashboard | tenant administration tests | tenant summaries and lifecycle actions remain available to platform administration |
| Membership RBAC | membership foundation tests | roles are seeded; users may hold multiple organization memberships; revocation persists |
| Membership enforcement | membership authorization tests | tenant login/session authorization requires active membership and uses membership role |
| Platform boundary | platform admin tests | platform-super-admin scope is separate from tenant/customer authorization |
| Legacy-session migration | legacy-session regression test | HTTP request handling contains no direct legacy `current_user()` reads |
| Sprint 1 compatibility | `make test` | all protected Sprint 1 authentication/admin/customer behavior remains green |
| Infrastructure validation | GitHub Actions `validate` | Terraform format/init/validation gate remains green |

## Release evidence

For the Sprint 2 closure PR, record:

1. the release candidate commit SHA;
2. successful GitHub Actions `smoke` result;
3. successful GitHub Actions `validate` result;
4. complete `make test` result from CI;
5. known limitations or deferred work;
6. rollback point (the last known-good `main` SHA before the release candidate).

Production deployment evidence is recorded only when a deployment is actually performed; CI success must not be described as production verification.

## Manual smoke checks after deployment

- each configured tenant domain resolves the expected tenant;
- an unknown/unconfigured host is rejected;
- customer login works for an active membership;
- revoked membership cannot authenticate into that tenant;
- customer dashboard/history contains only that tenant's activity;
- bootstrap platform admin can open tenant administration;
- customer/tenant cookies do not grant platform administration;
- suspend/reactivate behavior matches the documented lifecycle rules;
- Sprint 1 Solutions customer/admin journeys still function.

## Exit rule

Sprint 2 regression evidence is complete when the full suite and CI gates are green, the release/rollback documentation identifies the exact release candidate and rollback point, and any manual production-only checks are explicitly marked pending or completed rather than inferred.
