# S8-T04 Stripe Integration Boundary

## Purpose

S8-T04 introduces the payment-provider integration boundary without introducing product-level checkout or webhook reconciliation behavior.

The application now depends on a narrow provider-neutral interface. Stripe-specific configuration and transport are isolated in `stripe_provider.py`.

## Secret handling

Stripe credentials are loaded from environment variables only:

- `STRIPE_SECRET_KEY`;
- `STRIPE_WEBHOOK_SECRET`;
- optional `STRIPE_API_BASE`;
- optional `STRIPE_TIMEOUT_SECONDS`.

No Stripe secret, webhook secret, raw payment method, card number, CVC/CVV, bank account number, or routing number is persisted by this boundary.

## Provider-neutral interface

`billing_provider.py` defines:

- bounded provider operations;
- request/response dataclasses;
- controlled provider errors;
- transport-independent execution;
- recursive rejection of raw payment credential fields.

The current operation vocabulary is intentionally narrow:

- `customer.create`;
- `checkout_session.create`;
- `subscription.retrieve`;
- `invoice.retrieve`.

Business workflows do not call these operations directly until later Sprint 8 tasks add explicit authorization and reconciliation around them.

## Stripe adapter

`StripeBillingProvider`:

- validates HTTPS API configuration;
- uses bearer-key authentication;
- supports injected transport for tests;
- converts network/provider failures into controlled billing-provider errors;
- rejects incomplete provider objects;
- validates returned provider IDs as bounded opaque references.

The default transport uses Python's standard library HTTPS client and form encoding. CI uses a fake transport and performs no real Stripe calls.

## Failure behavior

Timeouts and OS/network failures become `BillingProviderUnavailable`.

HTTP failures and malformed/incomplete provider payloads become `BillingProviderError`.

Provider error bodies are not copied into application exceptions, reducing accidental secret or sensitive-data leakage.

## Security constraints

- provider state remains non-authoritative for application access;
- tenant authorization remains outside the provider adapter;
- raw payment/card/bank fields are rejected before transport;
- provider IDs are references only;
- production credentials remain environment/secret-manager inputs;
- CI performs no chargeable provider operations.

## Handoff to S8-T05

S8-T05 may add authorized Stripe customer and checkout onboarding using this provider boundary.

That task must require owner/admin authorization, validate same-tenant plan/subscription context, allow-list return URLs, and avoid activating entitlements solely from a provider response.
