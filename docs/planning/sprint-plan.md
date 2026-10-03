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

Sprint 3 — Site Builder is complete at the repository/CI level.

### Objective achieved

The platform now supports tenant-owned sites, domain-to-site resolution, site branding, navigation, pages, services/forms, media references, membership-authorized Site Builder administration, public rendering for published non-Solutions sites, and a non-destructive staged Solutions migration.

### Closure evidence

See [Sprint 3 Closure Record](../09-release/sprint-3-closure.md).

Repository/CI acceptance is complete at `79549d38741a167198146c601c0fdb32b039dbdb`. Production/manual smoke evidence and the separate Solutions Site Builder cutover remain deployment-time work.

## Sprint 4 status

Sprint 4 — CRM is the active planning/implementation Sprint.

### Objective

Manage tenant-scoped contacts, companies, opportunities, tasks, notes/timelines, and quote foundations while preserving protected customer, messaging, Site Builder, and platform-admin behavior.

### Locked plan

See [Sprint 4 Plan — CRM](sprint-4-plan.md).

### Current step

S4-T11 — Sprint 4 regression and closure.

This step enforces the focused Sprint 4 CI gate and records repository/CI acceptance, rollback boundaries, compatibility decisions, and deployment limitations.

### Protected baselines

- Sprint 1 customer/admin journeys remain protected.
- Sprint 2 tenant resolution, data isolation, membership authorization, and platform-admin separation remain protected.
- Sprint 3 Site Builder/domain/rendering behavior remains protected.
