# Sprint 9 Plan — Bookings and Calendars

- Status: Active
- Epic: EP-012 — Bookings and Calendars
- Protected baselines: Sprints 1–8
- Sprint 8 repository/CI baseline: `0751ac4c5cd3049473bada3c620052dbdad9ec88`

## Objective

Add tenant-safe scheduling that lets SMBs publish bookable services, manage staff/resource availability, prevent double-booking, and let customers book/reschedule/cancel without creating duplicate customer identity or calendar data silos.

## Entry criteria

- Sprint 8 is closed at repository/CI level.
- `make test` and `make test-sprint2` through `make test-sprint8` are protected.
- Tenant membership, Site Builder, CRM contacts, Customer Portal identities, notifications, billing, and audit boundaries already exist.
- Scheduling must reuse those boundaries instead of introducing parallel tenant/customer identity systems.

## Locked scope

Sprint 9 covers:

- scheduling tenant/timezone boundary;
- tenant calendars and bookable service types;
- staff/resource availability rules;
- conflict-safe appointments;
- public booking flow;
- authenticated customer reschedule/cancel;
- staff/admin calendar operations;
- reminder/notification integration;
- ICS calendar export;
- optional CRM/customer linkage;
- focused Sprint 9 regression and closure.

## Explicit non-scope

- two-way Google/Microsoft calendar synchronization;
- external OAuth calendar credentials;
- marketplace scheduling;
- payment capture/deposits for appointments;
- automated overbooking;
- AI-selected appointment times;
- medical/clinical scheduling semantics;
- deleting customer history when appointments are canceled.

## Time and safety principles

1. Persist canonical appointment timestamps as UTC epoch seconds.
2. Store an explicit IANA timezone for calendars and presentation.
3. DST conversion must use timezone-aware standard-library behavior.
4. Every scheduling record belongs to one active tenant.
5. Cross-tenant site/contact/customer/resource references fail closed.
6. Conflict checks occur server-side and are transactional.
7. Public booking never grants staff/admin authorization.
8. Existing CRM/customer identities are linked, not duplicated, when an authoritative match exists.
9. Cancel/reschedule preserves appointment audit history.
10. CI uses deterministic clocks/data and no external calendar provider.

## Task sequence

### S9-T01 — Scheduling tenant and time boundary

Define tenant authorization, same-tenant reference validation, UTC/IANA timezone rules, and threat/compatibility audit.

### S9-T02 — Calendars and service types

Add tenant calendars, optional Site Builder linkage, bookable service types, duration/buffer rules, lifecycle, and timezone settings.

### S9-T03 — Staff/resource availability

Add weekly availability, blackout periods, bounded booking horizon, minimum notice, and resource ownership.

### S9-T04 — Conflict-safe appointments

Add canonical appointment records, deterministic lifecycle, transactional overlap detection, and append-only transition history.

### S9-T05 — Public booking availability

Expose published service availability using safe public tenant/site context without leaking staff/customer/private calendar data.

### S9-T06 — Public booking creation

Allow a customer to claim a valid slot with bounded contact fields and optional safe linkage to an existing customer/contact.

### S9-T07 — Customer self-service

Add authenticated customer appointment listing, reschedule, and cancel with tenant/customer ownership checks.

### S9-T08 — Staff calendar administration

Add owner/admin/staff calendar views and authorized appointment management; viewers remain read-only where appropriate.

### S9-T09 — Reminders and notifications

Integrate appointment confirmation/reminder metadata with existing notification foundations without storing provider credentials.

### S9-T10 — Calendar export and integrations boundary

Add safe ICS export/feed foundations and define future external-calendar OAuth/synchronization boundary without implementing credentials.

### S9-T11 — Sprint 9 regression and closure

Add `make test-sprint9`, enforce CI, record rollback/known-limitations evidence, and formally close Sprint 9.

## Testing requirements

- `make test` remains the full regression gate.
- Sprint 2–8 focused gates remain protected.
- Sprint 9 adds `make test-sprint9`.
- Tests cover cross-tenant reference attempts, timezone/DST cases, overlapping bookings, simultaneous slot claims, customer ownership, canceled/rescheduled history, and public-data minimization.
- No test requires Google/Microsoft calendar credentials or real email/SMS delivery.

## Exit criteria

1. Tenant-owned calendars/services/availability/appointments exist.
2. UTC/IANA timezone handling is deterministic and tested.
3. Double-booking is prevented server-side.
4. Public and customer booking flows preserve tenant/customer isolation.
5. Staff administration is least-privilege.
6. Reminder/export foundations exist without external credentials.
7. Full protected regression evidence is green.
8. Closure/rollback evidence is recorded.
