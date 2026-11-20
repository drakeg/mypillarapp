# S8-T10 Billing Operations, Recovery, and Rollback

## Purpose

S8-T10 adds provider-independent operational controls for safely diagnosing and recovering Sprint 8 billing behavior without exposing secrets or persisting raw provider payloads.

## Maintenance mode

Set `MADMALLARD_BILLING_MAINTENANCE=true` to block provider write operations before transport.

The maintenance guard currently blocks:

- customer creation;
- checkout-session creation.

Read/retrieval operations remain available so operators can inspect provider state during an incident.

Maintenance failures return a controlled `BillingProviderUnavailable` error and do not call the provider transport.

## Rejected webhook retry

Rejected Stripe events can be retried only through an explicitly requested retry path.

Retry requirements:

- the payload must again pass Stripe signature verification;
- the existing provider event must have status `rejected`;
- event ID, event type, event creation timestamp, and provider object reference must exactly match the original rejected event;
- non-rejected events remain idempotent and are not replayed.

This allows recovery after fixing local configuration/ownership data while preventing an attacker or operator mistake from reusing an old event ID with different content.

Raw webhook payloads are still not stored.

## Operational summary

Owner/admin billing operators can request a tenant-scoped operational summary containing:

- maintenance-mode status;
- provider-event counts by status;
- subscription counts by status;
- invoice counts by status;
- bounded rejected provider-event references that were already resolved to that tenant.

Unresolved rejected events remain tenantless and are deliberately excluded from tenant-level diagnostics.

The summary contains no provider secrets, webhook signatures, raw payloads, card/bank data, or customer payment-method details.

## Recovery guidance

### Rejected webhook

1. Diagnose and correct the local ownership/configuration issue.
2. Obtain a fresh provider redelivery of the same event payload/signature.
3. Retry through the explicit rejected-event retry path.
4. Confirm the event transitions from rejected to processed/ignored.
5. Verify subscription/invoice/application state.

### Past-due recovery

A newer authenticated subscription event may move `past_due` back to `active` according to the deterministic application transition table.

Operators should not edit provider IDs or subscription status directly.

### Cancellation

Canceled application subscription records remain retained as history.

A new subscription may later be created through the normal checkout/reconciliation workflow. Tenant data is not deleted by cancellation.

## Rollback

If provider writes must be stopped immediately:

1. enable `MADMALLARD_BILLING_MAINTENANCE`;
2. keep signed webhook reconciliation available so state can continue to converge;
3. inspect tenant-scoped operational summaries;
4. correct or roll back the faulty application/provider configuration;
5. disable maintenance only after validation.

No recovery procedure requires payment credentials in application persistence.
