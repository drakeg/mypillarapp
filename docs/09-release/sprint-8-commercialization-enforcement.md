# S8-T08 Quotas and Commercialization Enforcement

## Purpose

S8-T08 connects deterministic Sprint 8 entitlements to live product enforcement without weakening existing tenant authorization.

## Site quota enforcement

`tenant_sites.create_site()` now evaluates the tenant's `sites` entitlement before creating a non-archived site.

Behavior:

- unassigned/internal tenants retain the explicit unlimited compatibility policy;
- assigned plans with a numeric site quota cannot exceed that quota;
- archived sites do not count toward the active site limit;
- quota failure occurs before the new site row is written.

The seeded `main` site counts toward the quota because it is a usable tenant site even while draft.

## AI commercialization enforcement

`ai_execution.execute()` now enforces Sprint 8 plan entitlements in addition to the existing Sprint 7 tenant AI settings.

Before a provider call:

- the plan-level `ai` entitlement must be enabled;
- the plan-level `ai_rolling_units` quota must allow requested rolling usage;
- existing tenant AI settings must still allow the request.

This makes the effective AI limit the stricter of the commercial plan and tenant-level AI controls.

A tenant administrator cannot raise local AI settings above a commercial plan's rolling ceiling.

## Internal compatibility

Unassigned/internal tenants retain the Sprint 8 internal policy:

- unlimited billing-layer site quota;
- AI allowed by billing policy;
- AI still requires the existing tenant AI setting to be enabled.

No existing tenant is silently commercialized or restricted merely by deploying Sprint 8.

## Failure behavior

Site and AI quota checks fail before consequential writes/provider calls.

AI plan failures are recorded through the existing AI execution rejection/quota ledger path.

Billing entitlements do not bypass existing tenant membership, site authorization, AI authorization, or kill-switch controls.

## Regression evidence

`tests/test_sprint8_commercialization_enforcement.py` verifies:

- internal tenant site compatibility;
- commercial site quota enforcement;
- archived-site quota release;
- disabled plan AI blocks before provider calls;
- plan rolling AI quota blocks before provider calls;
- tenant AI settings can remain stricter than the plan;
- unassigned/internal AI remains usable when explicitly enabled.

Focused validation also protects existing Sprint 3 site and Sprint 7 AI execution/settings tests.
