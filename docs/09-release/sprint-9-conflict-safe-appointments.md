# S9-T04 Conflict-Safe Appointment Lifecycle

## Purpose

S9-T04 adds canonical tenant-owned appointments with serialized resource conflict checks and append-only lifecycle transitions.

## Appointment ownership

Every appointment belongs to:

- one active tenant;
- one tenant-owned calendar;
- one non-archived service type;
- one active service-eligible resource.

Optional authenticated-customer and CRM-contact links must belong to the same tenant.

## Canonical times

Appointments persist:

- service start/end as UTC epoch seconds;
- conflict block start/end as UTC epoch seconds;
- a snapshot of service duration and before/after buffers.

The snapshot means a later service-duration or buffer edit does not silently change the historical appointment or its original conflict boundary.

## Conflict safety

Appointment creation uses an immediate SQLite write transaction.

Before insert, the transaction revalidates service/resource ownership and rejects overlap with an existing blocking appointment on the same resource.

Blocking states are:

- pending;
- confirmed.

Canceled, completed, and no-show appointments do not reserve a future resource interval.

Overlap uses half-open interval semantics:

`existing.block_start < requested.block_end && existing.block_end > requested.block_start`

Therefore exactly adjacent buffered intervals do not conflict.

## Lifecycle

New appointments may begin only as pending or confirmed.

Allowed transitions:

- pending → confirmed;
- pending → canceled;
- confirmed → canceled;
- confirmed → completed;
- confirmed → no_show.

Canceled/completed/no_show are terminal.

Each creation/status change writes an append-only transition record with optional authorized staff actor and bounded reason.

## Authorization boundary

When an actor is supplied, the actor must have scheduling `manage` capability in the same tenant.

Public/customer booking flows introduced later may create appointments through a higher-level facade with no staff actor, while still being subject to the same resource/conflict boundary.

## Deferred

Public slot generation, minimum-notice/horizon enforcement, public booking contact capture, customer reschedule/cancel, reminders, and ICS export remain later Sprint 9 tasks.

## Regression evidence

`tests/test_sprint9_scheduling_appointments.py` covers duration/buffer snapshots, buffered conflicts, exact-adjacent acceptance, cancellation releasing capacity, service-resource eligibility, cross-calendar denial, cross-tenant customer/contact denial, tenant-scoped reads, deterministic terminal lifecycle, append-only transitions, actor authorization, and bounded list filtering.
