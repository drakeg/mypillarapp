# S8-T06 Stripe Webhook Verification and Reconciliation

## Purpose

S8-T06 adds authenticated, idempotent Stripe webhook processing and verified reconciliation into application-owned billing state.

## Signature verification

Webhook payloads are verified with Stripe's timestamped HMAC-SHA256 signature format before JSON parsing or reconciliation.

Verification requires:

- configured webhook secret;
- valid `t=` timestamp;
- one or more `v1=` signatures;
- signature match using constant-time comparison;
- timestamp within the configured tolerance window.

Invalid or stale signatures fail before application state is touched.

## Event idempotency

Every provider event is recorded by `provider_name + event_ref` with a unique constraint.

Duplicate delivery returns the already-recorded result and does not create a second subscription or repeat state changes.

Provider-event records contain only event metadata required for operations:

- provider;
- event reference/type/time;
- resolved tenant when known;
- provider object reference;
- processing status/detail;
- received timestamp.

Raw webhook payloads are not persisted.

## Checkout reconciliation

`checkout.session.completed` resolves the tenant from the locally persisted checkout-session reference, not from untrusted provider metadata.

The event must match:

- exactly one local Stripe checkout session;
- the locally stored provider customer reference when supplied;
- tenant metadata when supplied;
- a provider subscription reference.

Only after successful signature and ownership verification does reconciliation:

- mark the local checkout completed;
- assign the selected application-owned plan;
- create an active application subscription;
- retain the provider customer/subscription references as opaque identifiers;
- record the provider event baseline for ordering.

The checkout initiator remains recorded for the initial application subscription audit entry.

## Subscription reconciliation

Supported Stripe subscription events are:

- `customer.subscription.created`;
- `customer.subscription.updated`;
- `customer.subscription.deleted`.

The provider subscription reference must resolve to exactly one application subscription. Customer and tenant metadata are checked when present.

Stripe states are mapped into the existing deterministic application lifecycle. Invalid lifecycle transitions fail closed.

## Replay and event ordering

Each application subscription stores the latest reconciled provider event timestamp/reference.

A later delivery with an event timestamp less than or equal to the latest applied provider event is safely ignored as stale/out-of-order.

This prevents an older replay from reversing newer application billing state.

## Invoice and unsupported events

Invoice events are authenticated and audited but intentionally ignored until S8-T07 adds tenant-safe invoice/payment-history metadata.

Other unsupported events are safely ignored and audited.

## Cross-tenant protections

Provider metadata is never trusted as tenant authorization.

Tenant resolution comes from application-owned checkout/subscription references. Supplied tenant/customer metadata may only confirm that ownership; mismatches are rejected.

Unknown or ambiguous provider references fail closed.

## Regression evidence

`tests/test_sprint8_stripe_webhooks.py` covers:

- valid signature verification;
- invalid/stale signature rejection;
- verified checkout reconciliation;
- duplicate-event idempotency;
- tenant metadata mismatch rejection;
- stale/out-of-order subscription events;
- newer subscription state reconciliation;
- safe audited invoice-event deferral.
