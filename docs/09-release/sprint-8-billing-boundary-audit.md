# S8-T01 Billing Tenant Boundary and Commercialization Audit

## Purpose

S8-T01 establishes the billing/commercialization security boundary before Stripe or any other payment provider is integrated.

No payment-provider calls, checkout sessions, webhooks, subscriptions, invoices, or chargeable actions are introduced in this task.

## Canonical billing ownership

Every future billing record must belong to exactly one active organization.

Billing access requires:

- an active application user;
- an active organization;
- an explicit active membership in that organization.

Billing administration is restricted to owner/admin roles.

Provider identifiers never replace tenant authorization.

## Eligible billing data classes

The boundary explicitly recognizes:

- plan;
- entitlement;
- subscription;
- invoice;
- license;
- provider customer reference;
- provider subscription reference;
- provider invoice reference;
- provider event reference.

Provider references are opaque bounded identifiers only.

They must never be treated as credentials or authorization.

## Prohibited payment data

Application persistence must not accept:

- card numbers;
- CVC/CVV;
- magnetic-stripe data;
- bank account numbers;
- routing numbers;
- payment-provider secret keys;
- webhook secrets;
- session tokens;
- raw payment-method payloads.

Future provider adapters must keep credentials in environment/secret-manager configuration.

## Legacy price and quote migration rules

Sprint 8 does not reinterpret existing commercial-looking records as billing authorization.

### CRM quotes

CRM quote totals are deterministic integer-cent estimate metadata.

A quote may be referenced by a later explicit billing workflow only after same-tenant validation.

A quote does not authorize a charge, subscription, invoice, entitlement, or license by itself.

### Creator storefront products

Storefront product prices are catalog metadata.

A product may be referenced only when the site and product belong to the same organization.

The presence of `price_cents` does not create a payment instruction or entitlement.

### Site service `price_text`

Legacy service `price_text` is presentation text only.

It is explicitly rejected as a canonical billing source and must never be parsed into charge amounts automatically.

## Provider state is not authorization

Stripe/customer/subscription/invoice IDs and webhook state are reconciliation inputs only.

Future application access must be granted by deterministic application-owned entitlement/subscription records after verified reconciliation.

A provider response or webhook can never directly bypass:

- tenant membership;
- application authorization;
- feature entitlement checks.

## Internal/non-commercial tenants

Existing tenants remain non-commercial unless explicitly assigned a Sprint 8 plan/subscription policy.

No existing tenant is automatically downgraded, disabled, charged, or migrated based on legacy price/catalog metadata.

## Failure and rollback rules

Billing/provider failures must not delete tenant data.

Billing-state transitions must be explicit, auditable, and reversible where policy permits.

Before any provider integration is introduced, future Sprint 8 tasks must preserve this boundary.

## Regression evidence

`tests/test_sprint8_billing_boundary.py` verifies:

- eligible vs prohibited billing data classification;
- explicit active tenant membership;
- owner/admin-only billing administration;
- opaque bounded provider references;
- same-tenant CRM quote validation;
- cross-tenant quote rejection;
- cross-tenant storefront product rejection;
- legacy service price text rejection;
- legacy prices cannot authorize charges;
- provider state cannot directly authorize application access.

## Handoff to S8-T02

S8-T02 may introduce deterministic application-owned plans and entitlements.

It must not require Stripe to evaluate current entitlement state and must preserve all S8-T01 ownership and migration rules.
