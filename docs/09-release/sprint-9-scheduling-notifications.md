# S9-T09 Appointment Confirmations and Reminders

## Purpose

S9-T09 adds deterministic appointment confirmation/reminder scheduling without embedding email/SMS/provider credentials in scheduling persistence.

## Scheduling notification ledger

Each notification belongs to one tenant-owned appointment and records:

- kind: confirmation or reminder;
- channel: email or in-app;
- scheduled UTC epoch;
- lifecycle status: scheduled, queued, suppressed, or canceled;
- optional existing Portal notification-delivery reference;
- timestamps.

No SMTP password, provider token, API key, webhook secret, or raw delivery credential is stored.

## Default timing

Initial appointment notification scheduling creates:

- confirmation at booking time;
- reminder 24 hours before the appointment when still future;
- reminder 60 minutes before the appointment when still future.

Reminder offsets are bounded, deterministic, and deduplicated.

## Authenticated customers

Appointments linked to an authenticated customer schedule email and in-app notices.

When due, authenticated notices delegate to the existing Customer Portal notification service using notification type `service_notice`.

Existing portal notification preferences remain authoritative:

- enabled notice → queued Portal delivery;
- disabled preference → scheduling notice marked suppressed;
- no separate scheduling preference system is introduced.

## Guest bookings

Guest bookings schedule email metadata only.

Due guest-email records expose the bounded guest snapshot, opaque booking reference, subject/body, and notification ID to an internal delivery-adapter boundary.

Scheduling does **not** automatically send guest email.

An explicit adapter may later queue the due guest email and mark the scheduling record queued. Provider credentials remain outside scheduling persistence.

## Lifecycle integration

- Public booking schedules initial confirmation/reminders.
- Staff-created appointments schedule initial confirmation/reminders.
- Canceled/completed/no-show appointments cancel still-scheduled notices.
- Customer cancellation cancels still-scheduled notices.
- Customer rescheduling cancels old scheduled reminders and creates new future reminders for the updated time while preserving completed/queued history.

## Content minimization

Notification text includes service name and appointment time in the calendar timezone.

It does not include internal resource IDs, user IDs, blackout reasons, provider secrets, or unrelated customer data.

## Regression evidence

`tests/test_sprint9_scheduling_notifications.py` covers guest metadata-only scheduling, explicit guest adapter queueing, authenticated Portal queue integration, Portal preference suppression, cancellation cleanup, customer-reschedule reminder rebuilding, and schema checks excluding provider secrets.
