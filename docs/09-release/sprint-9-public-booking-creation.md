# S9-T06 Public Booking Creation

## Purpose

S9-T06 turns advisory public availability into an authoritative booking claim without trusting the previously displayed capacity.

## Authoritative slot claim

A public booking request identifies only:

- tenant/site context;
- published calendar/service slugs;
- requested UTC service start;
- bounded guest contact fields.

Before creating an appointment the server re-evaluates:

- published site/calendar/service state;
- minimum notice and booking horizon;
- same-calendar eligible resources;
- weekly availability;
- blackouts;
- existing blocking appointments.

The final write uses the S9-T04 immediate-write appointment transaction, which rechecks service/resource ownership and overlap after acquiring the SQLite write lock.

Displayed public availability is therefore advisory, not authorization to claim a slot.

## Race handling

If more than one eligible resource can satisfy a slot, the booking layer tries them in deterministic order.

If a resource becomes unavailable between slot discovery and the authoritative insert, an `AppointmentConflictError` causes the request to try another eligible resource.

If all eligible resources are claimed, the request fails with `PublicSlotUnavailable`.

Resource identity is never returned to the public caller.

## Public booking reference

Successful public bookings receive a cryptographically random opaque reference.

The reference:

- is unique in application persistence;
- is not a customer-authentication credential;
- does not grant staff/customer portal authorization;
- is safe to return as the public booking confirmation identifier.

Later customer self-service must require authenticated customer ownership rather than treating this reference alone as identity proof.

## Guest contact snapshot

The appointment stores bounded public-booking contact fields:

- guest name;
- normalized email;
- optional normalized phone.

These fields are an appointment contact snapshot only.

A matching public email **does not** automatically:

- create an authenticated customer;
- link an existing customer account;
- link an existing CRM contact;
- grant portal access.

This prevents an unverified public email from becoming an identity-linking mechanism.

## Schema compatibility

Appointment schema initialization adds the new guest/reference columns when an older Sprint 9 appointment table is already present and creates a partial unique index for non-null public references.

Existing staff-created appointments remain valid with empty guest/reference fields.

## Public response minimization

The public booking response contains:

- opaque booking reference;
- calendar/service slugs;
- UTC start/end;
- display timezone;
- appointment status.

It does not expose appointment IDs, resource IDs/names, user IDs, CRM IDs, or internal availability details.

## Regression evidence

`tests/test_sprint9_public_booking.py` covers authoritative booking creation, guest normalization, opaque references, non-linking of matching customer/CRM email, remaining-resource selection, race fallback, all-resource race failure, unpublished/out-of-policy denial, guest validation, and schema migration/index presence.
