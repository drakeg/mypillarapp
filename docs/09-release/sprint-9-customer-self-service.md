# S9-T07 Authenticated Customer Scheduling Self-Service

## Purpose

S9-T07 lets an authenticated tenant customer adopt matching guest bookings and manage only those appointments through the existing Customer Portal identity boundary.

## Authentication and ownership

Customer self-service uses the existing revalidated `portal_tenancy.CustomerScope`.

The opaque public booking reference is **not** an authentication credential and is not sufficient for listing, canceling, or rescheduling an appointment.

All customer actions revalidate:

- active user;
- active tenant;
- active tenant membership;
- same-tenant appointment ownership.

## Guest booking claim

An authenticated customer may explicitly claim guest appointments whose normalized `guest_email` exactly matches the authenticated account email and whose appointment does not already have a customer owner.

Claiming:

- is tenant scoped;
- assigns `customer_user_id`;
- does not create a new customer identity;
- does not modify CRM ownership;
- does not cross email or tenant boundaries.

Once claimed, appointment ownership is the authenticated customer user ID rather than the guest email or public booking reference.

## Customer appointment listing

Customer listing delegates to the tenant-safe appointment model with the authenticated `customer_user_id` filter.

Other customers and foreign tenants cannot enumerate the appointment.

Canceled history may be included so rescheduling/cancellation history is not silently deleted.

## Customer cancellation

Only pending or confirmed owned appointments may be canceled.

Cancellation:

- uses an immediate write transaction;
- revalidates customer ownership inside the transaction;
- changes the appointment to canceled;
- records an append-only transition with the authenticated customer as actor;
- releases the resource interval for future booking.

Completed/no-show appointments cannot be canceled through self-service.

## Customer rescheduling

Rescheduling requires the appointment to remain pending/confirmed and the original site/calendar/service to remain publicly bookable.

The requested new time is re-evaluated through the S9-T05 public availability rules.

Eligible resources are tried in deterministic order. The final appointment update:

- uses an immediate write transaction;
- revalidates appointment ownership;
- revalidates service/resource eligibility;
- excludes the current appointment from its own conflict check;
- preserves the appointment's original duration/buffer snapshot;
- records an append-only `customer_rescheduled` audit event with the authenticated customer actor.

If another booking claims the first eligible resource, self-service may fall back to another eligible resource. If no resource remains, the reschedule fails closed.

## Data preservation

Cancellation and rescheduling preserve the original appointment record and transition history.

No customer history is deleted.

## Regression evidence

`tests/test_sprint9_customer_scheduling.py` covers explicit authenticated claim, email/tenant isolation, ownership-scoped listing, cancellation/capacity release, cross-customer denial, valid rescheduling, alternate-resource fallback, unpublished/out-of-policy denial, terminal-state restrictions, and customer actor audit evidence.
