# S8-T05 Stripe Customer and Checkout Onboarding

## Purpose

S8-T05 adds authorized Stripe customer and checkout-session onboarding while preserving the application-owned entitlement boundary.

A successful provider response creates only tenant-scoped provider/customer/checkout references. It does not assign a plan, create or activate a subscription, or enable application entitlements.

## Provider price mapping

Each tenant-owned plan may be mapped to a provider price reference for a named provider.

Mappings are tenant-scoped and require owner/admin billing authorization.

Provider price references are opaque identifiers only. They do not replace application plan ownership or entitlement checks.

## Provider customer creation

A tenant may have one provider customer reference per provider.

Customer creation:

- requires owner/admin billing scope;
- sends only bounded customer name/email plus tenant metadata to the provider;
- stores only the provider customer reference, provider name, actor, and timestamp;
- reuses the existing same-tenant customer reference for subsequent checkout sessions.

No card, bank, or raw payment-method data is accepted or persisted.

## Checkout creation

Checkout creation requires:

- active same-tenant application plan;
- same-tenant provider price mapping;
- owner/admin billing scope;
- provider customer reference;
- HTTPS success/cancel URLs whose hosts are explicitly allow-listed.

The checkout request uses subscription mode with one mapped provider price and tenant/plan metadata.

The application persists:

- tenant;
- plan;
- provider;
- provider customer reference;
- provider checkout-session reference;
- validated HTTPS checkout URL;
- local status `pending`;
- creating actor/timestamp.

## Return URL policy

Allowed return hosts come from either an explicit caller-provided set or `MADMALLARD_BILLING_RETURN_HOSTS`.

Return URLs:

- must use HTTPS;
- must not contain embedded credentials;
- must match an exact allow-listed host.

Provider checkout URLs must also use HTTPS.

## Non-authoritative provider response

A successful checkout-session response does not:

- assign the application plan;
- create an active application subscription;
- alter quotas;
- alter feature entitlements;
- bypass tenant membership or billing authorization.

S8-T06 webhook verification/reconciliation is responsible for authenticated provider-event processing before application billing state changes.

## Tenant isolation

Customer references, provider price mappings, and checkout sessions are keyed by organization.

Cross-tenant reads fail closed.

A provider price configured for one tenant cannot be used by another tenant even when plan slugs match.

## Regression evidence

`tests/test_sprint8_billing_checkout.py` covers:

- same-tenant provider price mapping;
- staff authorization denial;
- missing-price failure before provider call;
- provider customer creation/reuse;
- pending checkout persistence;
- HTTPS and allow-listed return URLs;
- provider checkout URL validation;
- no entitlement/plan activation from provider response;
- cross-tenant checkout isolation;
- cross-tenant provider price rejection.
