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

Sprint 1 is the active baseline.

### Objective

Provide a complete single-business operating loop for Mad Mallard Solutions.

### In scope

- public business site;
- contact and service requests;
- async conversations;
- optional response feedback;
- customer registration and authentication;
- email verification and password reset;
- customer dashboard and profile;
- separate admin authentication and dashboard;
- SES notification path;
- SSM-backed bootstrap admin secrets;
- Terraform/Docker/Caddy deployment;
- testing, runbooks, and release documentation.

### Out of scope

- multiple organizations;
- organization memberships;
- hostname-based tenant resolution;
- site builder;
- expanded CRM;
- projects and tickets;
- creator tools;
- AI;
- billing.

### Exit criteria

1. Customer journey works end to end.
2. Admin journey works end to end.
3. Deployment is reproducible.
4. No protected subsystem regressed.
5. Sprint 1 test plan passes.
6. Sprint 2 does not begin until Sprint 1 is formally closed.
