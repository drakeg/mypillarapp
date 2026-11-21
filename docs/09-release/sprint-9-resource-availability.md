# S9-T03 Scheduling Resources and Availability

## Purpose

S9-T03 adds tenant-owned schedulable resources, weekly availability windows, blackout periods, and service-to-resource eligibility.

## Resource model

Each resource belongs to one tenant-owned calendar and has:

- stable calendar-local slug;
- display name;
- kind: staff, room, equipment, or other;
- active/archived lifecycle;
- optional user linkage for staff resources only.

Staff resources must reference an active same-tenant owner/admin/staff membership. Viewer accounts and foreign-tenant users cannot become staff resources.

Non-staff resources do not carry user-account references.

## Weekly availability

Each resource may have multiple weekly availability windows using:

- weekday 0–6;
- start minute from local midnight;
- end minute from local midnight.

Windows are interpreted in the owning calendar's IANA timezone.

Overlapping windows for the same resource/day are rejected so later slot generation has one deterministic availability surface.

## Blackout periods

Blackouts are stored as canonical UTC epoch ranges and may carry a bounded reason.

Blackout filtering uses overlap semantics against requested UTC windows.

Archived resources cannot receive new availability or blackout records.

## Service eligibility

Bookable service types may be assigned to one or more active resources.

A service/resource mapping requires:

- same tenant;
- same calendar;
- non-archived service;
- active resource.

This supports later slot generation without allowing a service from one calendar to consume another calendar's resource.

## Existing calendar policy

Booking horizon and minimum notice remain tenant-calendar policy from S9-T02 and will be enforced when availability is transformed into public bookable slots.

## Deferred

Appointment persistence, transactional double-booking protection, public slot generation, customer self-service, reminders, and ICS export remain later Sprint 9 tasks.

## Regression evidence

`tests/test_sprint9_scheduling_availability.py` covers same-tenant staff-resource membership, viewer/foreign user rejection, non-user room resources, tenant/calendar isolation, overlapping weekly-window rejection, weekday/minute validation, UTC blackout filtering, same-calendar service/resource mapping, and archived-resource denial.
