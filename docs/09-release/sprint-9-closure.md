# Sprint 9 closure candidate — Bookings and Calendars

Status: pending green closure PR and recorded merge baseline.

## Delivered foundations
- Tenant scheduling authorization and UTC/IANA timezone conversion.
- Calendars, service types, resource eligibility, weekly availability and blackouts.
- Appointment lifecycle, buffered conflict checks and transition history.
- Public slot discovery and booking creation.
- Authenticated customer self-service and staff administration services.
- Confirmation/reminder metadata and Portal notification integration.
- Privacy-minimized ICS export and external-calendar protocol.

## Acceptance gate
Run `make test` and `make test-sprint2` through `make test-sprint9` using the repository-configured Python runtime. Require badge validation, Docker checks and Terraform validation. Record the successful workflow evidence and merge commit before marking this sprint complete.

## Deployment and limitations
Service-level regression coverage is not evidence of working browser journeys. Public booking, staff administration and customer self-service require deployed route/UI smoke tests. Guest reminder delivery and Google/Microsoft synchronization remain unimplemented external integration work. ICS export is not a live external synchronization service. Concurrent booking and tenant authorization deserve explicit release review; no real provider credentials are required for CI.

## Rollback
Restore the previous known-good application revision if scheduling causes a regression. Disable affected scheduling entrypoints before reopening booking traffic. Retain appointment and transition records; do not remove tenant data or scheduling tables as an automatic rollback. Verify existing tenant, CRM, portal and billing journeys before resuming service.

## Next priority
Prepare a usable scheduling experience with staff configuration, customer booking and appointment management screens; validate actual browser journeys before calling the feature commercially ready.
