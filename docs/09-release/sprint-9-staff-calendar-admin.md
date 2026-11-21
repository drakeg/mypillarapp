# S9-T08 Staff Calendar Administration

## Purpose

S9-T08 provides one least-privilege administration facade over the Sprint 9 scheduling models so the application UI does not call lower-level calendar/resource/appointment primitives without authorization.

## Role model

Scheduling administration reuses the S9-T01 tenant membership boundary:

- **viewer** — read-only scheduling overview;
- **staff** — read scheduling data and create/transition appointments;
- **owner/admin** — all staff capabilities plus calendar, service, resource, availability, blackout, and service/resource configuration.

Cross-tenant memberships fail closed.

The acting account parameter is named `actor_user_id` so it cannot be confused with the optional linked user account on a staff scheduling resource.

## Overview

The admin overview can return:

- tenant calendars;
- service types for an optionally selected calendar;
- resources for an optionally selected calendar;
- appointments, optionally bounded by a UTC time window.

When a calendar is selected, appointments are filtered to that calendar.

Unknown/foreign calendar IDs are not exposed as empty configuration objects; access fails closed.

## Configuration operations

Owner/admin-only facade operations include:

- create/update calendar;
- create/update service type;
- create resource;
- add weekly availability;
- add blackout period;
- map service to resource.

Each operation delegates to the existing tenant-safe Sprint 9 models.

## Appointment operations

Staff, owner, and admin may:

- create an appointment;
- transition an appointment through the S9-T04 lifecycle.

The facade records the authorized staff actor on appointment creation and transition history.

Viewers cannot create or modify appointments.

## Data safety

The facade does not broaden public/customer access.

Internal staff/resource identifiers remain visible only through authorized scheduling administration and are still hidden from public availability/booking responses.

## Regression evidence

`tests/test_sprint9_scheduling_admin.py` covers viewer read-only access, staff appointment management, staff configuration denial, owner/admin configuration, cross-tenant denial, selected-calendar appointment filtering, and unknown-calendar fail-closed behavior.
