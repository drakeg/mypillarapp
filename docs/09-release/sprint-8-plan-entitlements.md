# S8-T02 Plan and Entitlement Foundation

## Purpose

S8-T02 adds deterministic, application-owned billing plans and entitlements without requiring Stripe or any other provider to decide access.

## Tenant-owned plans

Plan definitions are owned by one organization.

A plan has:

- stable tenant-local slug;
- display name;
- active/archived lifecycle;
- commercial/non-commercial marker;
- bounded entitlement metadata;
- created/updated timestamps.

A tenant administrator cannot create or assign a plan owned by another organization.

## Supported entitlements

The initial entitlement set is intentionally bounded:

- `sites` — quota;
- `crm` — boolean;
- `portal` — boolean;
- `creator` — boolean;
- `ai` — boolean;
- `ai_rolling_units` — quota.

Unknown entitlements fail closed.

Quota values are non-negative integers with an explicit upper bound.

## Explicit tenant assignment

Commercial plan assignment is explicit and stored in `billing_tenant_plans`.

Each organization can have at most one current plan assignment in this foundation.

Assignment records include:

- organization;
- plan;
- assigning user;
- assignment timestamp.

Assignment requires an owner/admin billing scope.

## Internal/non-commercial compatibility

Existing organizations without a Sprint 8 plan assignment remain under an explicit internal compatibility policy.

The internal policy preserves existing features and does not impose commercial quotas:

- CRM enabled;
- Portal enabled;
- Creator enabled;
- AI enabled;
- site quota unlimited;
- AI rolling quota unlimited from the billing layer.

This compatibility policy prevents Sprint 8 from silently disabling existing tenants.

It is application policy only and is not inferred from payment-provider data.

## Deterministic entitlement decisions

`billing_plans.entitlement()` resolves an entitlement entirely from application-owned data.

Decision results expose:

- tenant;
- entitlement key;
- allowed/denied;
- optional quota;
- source (`internal_default`, `plan`, or `inactive_plan`);
- plan slug when applicable.

No provider API call is made or required.

## Server-side enforcement

`billing_plans.require_entitlement()` performs deterministic server-side checks.

Boolean entitlements fail closed when disabled.

Quota entitlements reject requests that exceed the assigned quota.

This foundation does not yet wire every product feature to plan enforcement; S8-T08 is responsible for selected product enforcement.

## Plan lifecycle

Active plans may be assigned.

Assigned plans cannot be archived.

Archived plans are not eligible for new assignments.

This avoids creating an assignment that immediately points at an inactive plan.

## Security and isolation

- plan definitions are tenant-owned;
- assignment is same-tenant only;
- owner/admin authorization is required for plan creation/assignment;
- staff cannot create or assign plans;
- unknown entitlement keys fail closed;
- missing/inactive organizations fail closed;
- provider state cannot override entitlement decisions.

## Regression evidence

`tests/test_sprint8_billing_plans.py` verifies:

- tenant-owned plan isolation;
- same slug may safely exist in different tenants;
- owner/admin administration only;
- explicit same-tenant assignment;
- existing internal tenant compatibility;
- deterministic provider-independent decisions;
- unknown entitlement denial;
- server-side quota enforcement;
- bounded entitlement metadata;
- assigned-plan archival denial.

## Handoff to S8-T03

S8-T03 may add application-owned subscription lifecycle records.

Subscription state must reference same-tenant plans and must not make provider metadata authoritative for tenant authorization.
