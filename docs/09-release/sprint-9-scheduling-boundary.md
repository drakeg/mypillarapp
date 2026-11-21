# S9-T01 Scheduling Tenant and Time Boundary

## Purpose

S9-T01 establishes the authorization, tenant ownership, and time-handling rules that all Sprint 9 booking/calendar records must follow.

## Authorization

Scheduling staff access reuses tenant memberships:

- owner/admin/staff may manage scheduling;
- viewers may read scheduling state but cannot mutate it;
- owner/admin may administer scheduling configuration;
- revoked/missing memberships fail closed;
- inactive/suspended organizations fail closed;
- platform administration is not a scheduling membership shortcut.

## Canonical time representation

Appointment and availability persistence uses integer UTC epoch seconds.

Calendars also store an explicit IANA timezone for user-facing interpretation. Local wall-clock input is converted with the Python standard library `zoneinfo` implementation.

Rules:

- timezone names must resolve as valid IANA zones;
- persisted start/end values must be ordered UTC epochs;
- local wall-clock times that do not exist because of a DST transition are rejected;
- presentation converts canonical UTC back into the calendar timezone;
- later scheduling models must not store ambiguous ad-hoc local-time strings as authoritative appointment time.

## Tenant-owned references

Scheduling may link to existing product records but may not reinterpret ownership.

The boundary currently validates optional links to:

- Site Builder sites;
- canonical CRM contacts;
- authenticated customer users.

Each linked record must belong to the same active organization. Archived sites/contacts and foreign-tenant records fail closed.

## Identity compatibility

Sprint 9 does not introduce a parallel customer identity system.

Public booking may collect bounded contact details later, but authoritative CRM/customer links must point to existing same-tenant records. Linking must never mutate a record in another tenant.

## Threats addressed

- cross-tenant appointment/customer linkage;
- hidden use of platform-admin identity as tenant staff;
- DST/nonexistent local-time errors;
- inconsistent local-time storage;
- stale archived site/contact references;
- foreign customer IDs supplied through public/staff requests.

## Deferred to later Sprint 9 tasks

- calendar/service persistence;
- weekly availability and blackout periods;
- overlap/conflict detection;
- public slot discovery;
- public booking writes;
- customer reschedule/cancel;
- reminders;
- ICS export and future external-calendar integration.

## Regression evidence

`tests/test_sprint9_scheduling_boundary.py` covers role authorization, inactive tenant denial, cross-tenant membership/reference rejection, UTC range validation, IANA timezone validation, UTC/local round-tripping, DST spring-forward gap rejection, and same-tenant Site Builder/CRM/customer linkage.
