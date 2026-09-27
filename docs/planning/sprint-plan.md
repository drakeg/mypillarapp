# Sprint Plan

## Method

Development uses goal-oriented Sprints. Each Sprint has locked scope, requirements, acceptance tests, deliverables, entry criteria, and exit criteria. New ideas go to the backlog unless required to meet the current Sprint goal.

## Definition of Sprint completion

- all requirements implemented;
- all acceptance tests pass;
- regression tests pass;
- documentation updated;
- deployment reproducible;
- release/rollback evidence recorded;
- no later-sprint functionality introduced;
- owner approves the demonstration.

## Sprint 1 status

Sprint 1 — Single-Business MVP is complete as the protected compatibility baseline.

Its public site, customer intake, messaging, customer authentication, dashboard/profile, bootstrap admin, SES/SSM integration, deployment, and regression behavior remain protected while Sprint 2 evolves the platform.

## Sprint 2 status

Sprint 2 — Multi-Tenant Foundation is complete as the protected multi-tenant baseline.

### Objective achieved

The platform now supports tenant/domain resolution, tenant-scoped customer data and authentication, organization memberships and roles, tenant lifecycle/administration, and a separate platform-super-admin boundary while preserving Sprint 1 compatibility.

### Completed implementation

- S2-T01 through S2-T03: tenant persistence, host resolution, and request context;
- S2-T04 through S2-T07: tenant-scoped conversations, public request flow, customer isolation, and auth links;
- S2-T08 through S2-T10: tenant-scoped identities, organization management, and branding;
- S2-T11 through S2-T13: onboarding, lifecycle management, and tenant administration dashboard;
- S2-T14 through S2-T17: membership RBAC, membership-aware authorization, platform-super-admin boundary, and legacy session-read migration;
- S2-T18 through S2-T19: regression evidence and enforced CI closure gates;
- S2-T20: formal closure evidence and handoff to Sprint 3.

### Closure evidence

See [Sprint 2 Closure Record](../09-release/sprint-2-closure.md).

Repository/CI acceptance is complete. Production deployment/manual smoke evidence remains deployment-time work and must not be inferred from CI.

## Sprint 3 status

Sprint 3 — Site Builder is the active planning/implementation Sprint.

### Objective

Allow each organization to configure a distinct public site while preserving the Sprint 1 customer/admin baseline and Sprint 2 tenant-isolation guarantees.

### Locked plan

See [Sprint 3 Plan — Site Builder](sprint-3-plan.md).

### Current step

S3-T10 — Existing Solutions migration.

This step stages the existing Solutions homepage content as draft Site Builder records while keeping the static live homepage and its intake/chat/customer journeys unchanged. Cutover remains separately gated by parity and manual smoke evidence.

### Protected baselines

- Sprint 1 customer/admin journeys remain protected.
- Sprint 2 tenant resolution, tenant data isolation, membership authorization, and platform-admin separation remain protected.
