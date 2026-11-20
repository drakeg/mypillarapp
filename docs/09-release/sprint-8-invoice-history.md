# S8-T07 Invoice and Payment-History Metadata

## Purpose

S8-T07 adds tenant-visible invoice/payment history from authenticated Stripe invoice events without persisting raw payment credentials or payment-method details.

## Stored metadata

The application stores only bounded invoice metadata needed for tenant administration:

- provider invoice reference;
- provider customer/subscription references;
- application subscription/tenant ownership;
- invoice status;
- three-letter currency code;
- amount due/paid/remaining in integer minor units;
- hosted invoice URL;
- invoice PDF URL;
- due/paid timestamps;
- latest provider event timestamp/reference;
- local created/updated timestamps.

Raw webhook payloads, card numbers, CVC/CVV, bank data, payment method payloads, or provider secrets are not stored.

## Tenant resolution

Invoice ownership is resolved from the application-owned subscription matching the provider subscription reference.

Provider metadata may confirm ownership but cannot select a tenant.

Customer references must match the locally stored provider customer when both are present.

Unknown, ambiguous, or cross-tenant references fail closed.

## Supported invoice events

Authenticated Stripe webhook processing handles:

- `invoice.created`;
- `invoice.finalized`;
- `invoice.paid`;
- `invoice.payment_failed`;
- `invoice.voided`;
- `invoice.marked_uncollectible`.

Other authenticated `invoice.*` events are ignored and audited until explicitly supported.

## Ordering and replay

Each invoice stores its latest applied provider event timestamp/reference.

Older or equal-timestamp events are treated as stale/out-of-order and do not overwrite newer invoice state.

Provider event IDs remain globally idempotent through the S8-T06 provider-event ledger.

## URL validation

Hosted invoice and PDF references must:

- use HTTPS;
- include a hostname;
- contain no embedded username/password credentials.

Invalid references reject reconciliation rather than being persisted.

## Billing history reads

`billing_invoices.list_invoices()` and `get_invoice()` require owner/admin billing authorization.

Reads are tenant-scoped and list requests are capped at 100 records.

Staff/viewers cannot read the billing history through this API.

## Regression evidence

Invoice/webhook tests verify:

- authenticated invoice reconciliation;
- tenant/customer mismatch rejection;
- owner/admin-only reads;
- cross-tenant isolation;
- HTTPS invoice-link validation;
- integer amount metadata;
- stale/out-of-order event protection;
- existing checkout/subscription/provider boundaries remain green.
