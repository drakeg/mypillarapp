# S9-T05 Public Booking Availability

## Purpose

S9-T05 exposes privacy-safe, read-only public service availability for published tenant sites without leaking staff/resource identity or internal scheduling data.

## Public service catalog

A service is public only when:

- the Site Builder site is published;
- the scheduling calendar is published and linked to that site;
- the service type is published.

Public service metadata contains only:

- calendar slug/name/timezone;
- service slug/name/description;
- service duration.

Internal calendar IDs, resource IDs, staff user IDs, customer records, blackout details, and internal lifecycle records are not exposed.

## Slot generation

Public slots are derived from:

- same-calendar service/resource eligibility;
- weekly resource availability in the calendar's IANA timezone;
- service duration and before/after buffers;
- calendar minimum notice;
- calendar booking horizon;
- UTC blackout periods;
- blocking pending/confirmed appointments.

Candidate local availability windows are converted through the S9-T01 timezone boundary and emitted as canonical UTC service start/end values.

## Capacity privacy

When multiple resources can satisfy the same slot, the public result reports only `available_resource_count`.

It never returns:

- resource IDs/slugs/names;
- linked staff user IDs/names;
- blackout reasons;
- appointment/customer details.

This lets a later booking transaction select a resource internally without disclosing internal staffing structure.

## Bounds

Public availability requests:

- require an ordered UTC window;
- are limited to 31 days per query;
- are further clipped by the calendar's minimum notice and booking horizon;
- use a bounded 5–120 minute slot step in five-minute increments.

## Conflict performance

Availability generation bulk-loads each resource's blackout and blocking appointment intervals once per request rather than reopening the schema/database for every candidate slot.

This public result is advisory only. S9-T06 booking creation will still use the S9-T04 immediate-write transaction as the authoritative conflict check.

## Regression evidence

`tests/test_sprint9_public_availability.py` covers:

- published-only site/calendar/service exposure;
- unpublished-site denial;
- anonymous resource-capacity aggregation;
- resource identity/data minimization;
- minimum notice;
- booking horizon;
- blackout capacity reduction;
- existing appointment capacity reduction;
- complete slot removal when all eligible resources are unavailable;
- bounded public windows;
- cross-tenant/site denial.
