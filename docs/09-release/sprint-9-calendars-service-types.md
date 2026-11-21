# S9-T02 Calendars and Bookable Service Types

## Purpose

S9-T02 adds the canonical tenant-owned calendar and service-type records that later Sprint 9 availability and appointment logic will use.

## Calendar model

Each calendar belongs to one active organization and may optionally link to one same-tenant, non-archived Site Builder site.

Calendar fields include:

- tenant ownership;
- optional site reference;
- stable tenant-unique slug;
- display name;
- IANA timezone;
- lifecycle status: draft, published, archived;
- booking horizon in days;
- minimum booking notice in minutes;
- created/updated timestamps.

A calendar timezone is presentation/configuration metadata. Appointment timestamps remain canonical UTC under S9-T01.

## Service type model

Each service type belongs to exactly one tenant-owned calendar.

Service fields include:

- tenant ownership;
- calendar ownership;
- calendar-local stable slug;
- display name/description;
- duration in minutes;
- buffer before/after in minutes;
- lifecycle status;
- created/updated timestamps.

Duration is bounded to 5–1440 minutes and each buffer to 0–1440 minutes.

## Tenant isolation

- calendar reads are filtered by organization;
- site links must belong to the same organization;
- service reads/writes require a same-tenant calendar;
- the same calendar slug may exist in different tenants;
- the same service slug may exist on different calendars;
- foreign calendar IDs cannot be used to create services.

## Lifecycle

Draft/published records may be updated. Archived calendars/services are immutable through the model API.

Published-only list filters are provided for future public booking surfaces.

Archiving a calendar prevents creation or mutation of services on that calendar but preserves existing records for audit/history.

## Deferred

Availability, blackout periods, appointment persistence, conflict detection, public booking, customer self-service, reminders, and ICS export remain later Sprint 9 tasks.

## Regression evidence

`tests/test_sprint9_scheduling_calendars.py` covers tenant/site scoping, timezone/horizon/notice validation, slug uniqueness, publication filters, archive immutability, duration/buffer bounds, cross-tenant service denial, and parent-calendar lifecycle enforcement.
