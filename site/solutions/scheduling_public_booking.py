from __future__ import annotations

from dataclasses import dataclass
import re
import secrets
import time

import scheduling_appointments
import scheduling_notifications
import scheduling_public


_EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


class PublicSlotUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class PublicBooking:
    reference: str
    calendar_slug: str
    service_slug: str
    start_at: int
    end_at: int
    timezone: str
    status: str


def create_public_booking(
    organization_slug: str,
    site_slug: str,
    *,
    calendar_slug: str,
    service_slug: str,
    start_at: int,
    guest_name: str,
    guest_email: str,
    guest_phone: str = '',
    now: int | None = None,
) -> PublicBooking:
    clean_name = _name(guest_name)
    clean_email = _email(guest_email)
    clean_phone = _phone(guest_phone)
    current = int(time.time()) if now is None else int(now)

    calendar, service, resources = (
        scheduling_public._eligible_resources_for_slot(
            organization_slug,
            site_slug,
            calendar_slug=calendar_slug,
            service_slug=service_slug,
            start_at=start_at,
            now=current,
        )
    )
    if calendar is None or service is None or not resources:
        raise PublicSlotUnavailable(
            'The requested public booking slot is not available.'
        )

    for resource in sorted(resources, key=lambda item: item.id):
        try:
            appointment = scheduling_appointments.create_appointment(
                organization_slug,
                service_id=service.id,
                resource_id=resource.id,
                start_at=int(start_at),
                status='confirmed',
                public_ref=_new_reference(),
                guest_name=clean_name,
                guest_email=clean_email,
                guest_phone=clean_phone,
                customer_user_id=None,
                crm_contact_id=None,
                actor_user_id=None,
                reason='public_booking',
            )
        except scheduling_appointments.AppointmentConflictError:
            continue
        scheduling_notifications.schedule_initial_notifications(
            organization_slug,
            appointment.id,
            now=current,
        )
        return PublicBooking(
            reference=appointment.public_ref,
            calendar_slug=calendar.slug,
            service_slug=service.slug,
            start_at=appointment.start_at,
            end_at=appointment.end_at,
            timezone=calendar.timezone,
            status=appointment.status,
        )

    raise PublicSlotUnavailable(
        'The requested public booking slot was claimed by another booking.'
    )


def _new_reference() -> str:
    return secrets.token_urlsafe(18)


def _name(value: str) -> str:
    clean = (value or '').strip()
    if not clean:
        raise ValueError('Guest name is required.')
    if len(clean) > 200:
        raise ValueError('Guest name must be 200 characters or fewer.')
    return clean


def _email(value: str) -> str:
    clean = (value or '').strip().lower()
    if not clean:
        raise ValueError('Guest email is required.')
    if len(clean) > 320 or not _EMAIL_RE.fullmatch(clean):
        raise ValueError('Guest email is invalid.')
    return clean


def _phone(value: str) -> str:
    clean = (value or '').strip()
    if not clean:
        return ''
    digits = ''.join(ch for ch in clean if ch.isdigit())
    if len(digits) < 7 or len(digits) > 15:
        raise ValueError('Guest phone must contain 7 to 15 digits.')
    return ('+' if clean.startswith('+') else '') + digits
