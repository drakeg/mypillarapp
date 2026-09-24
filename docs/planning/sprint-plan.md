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

Sprint 2 — Multi-Tenant Foundation is the active implementation baseline.

### Objective

Support multiple businesses safely in one deployment while preserving the stable Sprint 1 customer and admin journeys.

### Completed foundation

- S2-T01 through S2-T03: tenant persistence, host resolution, and request context;
- S2-T04 through S2-T07: tenant-scoped conversations, public request flow, customer isolation, and auth links;
- S2-T08 through S2-T10: tenant-scoped identities, organization management, and branding;
- S2-T11 through S2-T13: onboarding, lifecycle management, and tenant administration dashboard;
- S2-T14: membership-based tenant authorization / RBAC foundation;
- S2-T15: membership-aware tenant authorization enforcement.

### Current step

S2-T16 — Platform super-admin boundary.

The current step makes the bootstrap administrator an explicit platform-scoped identity. Tenant lifecycle, managed-site configuration, and platform settings require the platform super-admin scope, while organization membership roles remain tenant-scoped and cannot grant platform control.

### Sprint 2 remaining scope

- completion of multi-tenant migration and regression evidence;
- Sprint 2 release/rollback documentation and closure.

### Out of scope

- site builder;
- expanded CRM;
- projects and tickets beyond current request flows;
- creator tools;
- AI;
- billing.

### Exit criteria

1. Tenant resolution and data isolation work end to end.
2. Users can hold organization-specific roles without cross-tenant leakage.
3. Platform-level administration remains separated from tenant authorization.
4. Existing Sprint 1 customer/admin behavior does not regress.
5. Sprint 2 regression plan passes.
6. Sprint 3 does not begin until Sprint 2 is formally closed.
