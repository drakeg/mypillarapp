# S9-T10 Calendar Export and Integrations Boundary

## Purpose

S9-T10 adds privacy-safe iCalendar export foundations and a provider-neutral external-calendar integration boundary without storing OAuth credentials or implementing live synchronization.

## ICS export

Authorized scheduling viewers may export:

- one appointment as an `.ics` file;
- one tenant calendar over a bounded UTC window.

Exports use RFC-style iCalendar fields:

- VCALENDAR / VEVENT;
- stable UID derived from tenant + appointment ID;
- UTC DTSTAMP / DTSTART / DTEND;
- service name as SUMMARY;
- application-owned appointment status;
- escaped calendar/service text;
- CRLF line endings and folded long lines.

## Privacy

ICS export intentionally excludes:

- guest/customer names;
- customer email/phone;
- CRM identifiers;
- resource/staff identity;
- internal notes;
- public booking tokens;
- provider credentials.

The event description is a generic application-generated value.

## Tenant isolation

All export entrypoints require scheduling `view` authorization.

Appointment/calendar lookups remain tenant scoped. Cross-tenant export attempts fail closed.

Calendar export filters appointments to the selected tenant-owned calendar and requested UTC window.

## External-calendar boundary

`ExternalCalendarProvider` defines only the minimal future synchronization contract:

- upsert event;
- delete event.

The application-side sync payload includes only:

- stable UID;
- UTC start/end;
- service summary;
- generic description.

The provider boundary does not receive customer contact information or internal resource identity by default.

## External references

Provider event references are treated as opaque references only.

They are tenant-associated through an existing application-owned appointment and are never used as authorization.

Provider names and external references are bounded and validated.

## Explicitly not implemented

S9-T10 does not add:

- Google OAuth;
- Microsoft OAuth;
- refresh/access tokens;
- provider client secrets;
- two-way synchronization;
- webhook subscriptions;
- conflict resolution against external calendars;
- credential persistence.

Those require a later explicit integrations Sprint with secret-manager and OAuth threat modeling.

## Regression evidence

`tests/test_sprint9_calendar_integrations.py` verifies:

- valid private single-appointment ICS export;
- cross-tenant export denial;
- calendar/window filtering;
- canceled event status mapping;
- customer/resource privacy in sync payloads;
- tenant-scoped external event references;
- bounded export limits.
