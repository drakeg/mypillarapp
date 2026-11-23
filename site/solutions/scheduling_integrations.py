from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import scheduling_appointments
import scheduling_boundary
import scheduling_calendars


MAX_EXPORT_APPOINTMENTS = 1000


@dataclass(frozen=True)
class CalendarExport:
    filename: str
    content_type: str
    body: str


@dataclass(frozen=True)
class ExternalCalendarEvent:
    provider_name: str
    external_event_ref: str
    appointment_id: int


class ExternalCalendarProvider(Protocol):
    provider_name: str

    def upsert_event(
        self,
        *,
        uid: str,
        start_at: int,
        end_at: int,
        summary: str,
        description: str,
    ) -> str:
        ...

    def delete_event(
        self,
        external_event_ref: str,
    ) -> None:
        ...


def export_appointment(
    actor_user_id: int,
    organization_slug: str,
    appointment_id: int,
) -> CalendarExport:
    scope = scheduling_boundary.require(
        actor_user_id, organization_slug, 'view'
    )
    appointment = scheduling_appointments.get_appointment(
        scope.organization_slug, appointment_id
    )
    if appointment is None:
        raise PermissionError('Appointment export access denied.')
    service = scheduling_calendars.get_service_type(
        scope.organization_slug, appointment.service_id
    )
    calendar = scheduling_calendars.get_calendar(
        scope.organization_slug, appointment.calendar_id
    )
    if service is None or calendar is None:
        raise ValueError('Appointment export data is incomplete.')

    body = _calendar_document(
        calendar_name=calendar.name,
        events=[
            _event_lines(
                scope.organization_slug,
                appointment,
                service.name,
            )
        ],
    )
    return CalendarExport(
        filename=f'appointment-{appointment.id}.ics',
        content_type='text/calendar; charset=utf-8',
        body=body,
    )


def export_calendar(
    actor_user_id: int,
    organization_slug: str,
    calendar_id: int,
    *,
    start_at: int,
    end_at: int,
    include_canceled: bool = False,
    limit: int = MAX_EXPORT_APPOINTMENTS,
) -> CalendarExport:
    scope = scheduling_boundary.require(
        actor_user_id, organization_slug, 'view'
    )
    calendar = scheduling_calendars.get_calendar(
        scope.organization_slug, calendar_id
    )
    if calendar is None:
        raise PermissionError('Calendar export access denied.')

    start, end = scheduling_boundary.validate_utc_range(
        start_at, end_at
    )
    bounded_limit = _limit(limit)
    appointments = scheduling_appointments.list_appointments(
        scope.organization_slug,
        start_at=start,
        end_at=end,
        include_canceled=include_canceled,
    )
    appointments = [
        item for item in appointments
        if item.calendar_id == calendar.id
    ][:bounded_limit]

    events: list[list[str]] = []
    for appointment in appointments:
        service = scheduling_calendars.get_service_type(
            scope.organization_slug, appointment.service_id
        )
        if service is None:
            continue
        events.append(
            _event_lines(
                scope.organization_slug,
                appointment,
                service.name,
            )
        )

    body = _calendar_document(
        calendar_name=calendar.name,
        events=events,
    )
    return CalendarExport(
        filename=f'{_filename(calendar.slug)}.ics',
        content_type='text/calendar; charset=utf-8',
        body=body,
    )


def build_external_event(
    organization_slug: str,
    appointment_id: int,
    *,
    provider_name: str,
    external_event_ref: str,
) -> ExternalCalendarEvent:
    appointment = scheduling_appointments.get_appointment(
        organization_slug, appointment_id
    )
    if appointment is None:
        raise PermissionError(
            'External calendar appointment reference is not owned by tenant.'
        )
    provider = _provider(provider_name)
    external_ref = _external_ref(external_event_ref)
    return ExternalCalendarEvent(
        provider_name=provider,
        external_event_ref=external_ref,
        appointment_id=appointment.id,
    )


def sync_payload(
    organization_slug: str,
    appointment_id: int,
) -> dict[str, object]:
    appointment = scheduling_appointments.get_appointment(
        organization_slug, appointment_id
    )
    if appointment is None:
        raise PermissionError(
            'External calendar appointment reference is not owned by tenant.'
        )
    service = scheduling_calendars.get_service_type(
        organization_slug, appointment.service_id
    )
    if service is None:
        raise ValueError('Appointment service is unavailable.')

    return {
        'uid': _uid(organization_slug, appointment),
        'start_at': appointment.start_at,
        'end_at': appointment.end_at,
        'summary': service.name,
        'description': 'Scheduled through Mad Mallard Platform',
    }


def _calendar_document(
    *,
    calendar_name: str,
    events: list[list[str]],
) -> str:
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Mad Mallard Platform//Bookings//EN',
        'CALSCALE:GREGORIAN',
        f'X-WR-CALNAME:{_escape_text(calendar_name)}',
    ]
    for event in events:
        lines.extend(event)
    lines.append('END:VCALENDAR')
    return '\r\n'.join(_fold(line) for line in lines) + '\r\n'


def _event_lines(
    organization_slug: str,
    appointment: scheduling_appointments.Appointment,
    service_name: str,
) -> list[str]:
    lines = [
        'BEGIN:VEVENT',
        f'UID:{_uid(organization_slug, appointment)}',
        f'DTSTAMP:{_utc_stamp(appointment.updated_at)}',
        f'DTSTART:{_utc_stamp(appointment.start_at)}',
        f'DTEND:{_utc_stamp(appointment.end_at)}',
        f'SUMMARY:{_escape_text(service_name)}',
        'DESCRIPTION:Scheduled through Mad Mallard Platform',
        f'STATUS:{_ics_status(appointment.status)}',
        f'SEQUENCE:{max(0, int(appointment.updated_at) - int(appointment.created_at))}',
        'END:VEVENT',
    ]
    return lines


def _uid(
    organization_slug: str,
    appointment: scheduling_appointments.Appointment,
) -> str:
    slug = (organization_slug or '').strip().lower()
    return f'{appointment.id}.{slug}@madmallards.local'


def _utc_stamp(value: int) -> str:
    stamp = datetime.fromtimestamp(
        int(value),
        tz=timezone.utc,
    )
    return stamp.strftime('%Y%m%dT%H%M%SZ')


def _ics_status(value: str) -> str:
    clean = (value or '').strip().lower()
    if clean == 'canceled':
        return 'CANCELLED'
    if clean in {'confirmed', 'completed', 'no_show'}:
        return 'CONFIRMED'
    return 'TENTATIVE'


def _escape_text(value: str) -> str:
    return (
        str(value or '')
        .replace('\\', '\\\\')
        .replace(';', '\\;')
        .replace(',', '\\,')
        .replace('\r\n', '\\n')
        .replace('\r', '\\n')
        .replace('\n', '\\n')
    )


def _fold(line: str) -> str:
    encoded = line.encode('utf-8')
    if len(encoded) <= 75:
        return line

    pieces: list[str] = []
    current = ''
    for char in line:
        candidate = current + char
        if len(candidate.encode('utf-8')) > 75:
            pieces.append(current)
            current = char
        else:
            current = candidate
    pieces.append(current)
    return '\r\n '.join(pieces)


def _filename(value: str) -> str:
    clean = ''.join(
        char if char.isalnum() or char in {'-', '_'} else '-'
        for char in (value or '').strip().lower()
    ).strip('-')
    return clean or 'calendar'


def _limit(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError('Calendar export limit must be an integer.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Calendar export limit must be an integer.') from exc
    if clean < 1:
        raise ValueError('Calendar export limit must be at least 1.')
    return min(clean, MAX_EXPORT_APPOINTMENTS)


def _provider(value: str) -> str:
    clean = (value or '').strip().lower()
    if not clean or len(clean) > 40:
        raise ValueError('External calendar provider name is invalid.')
    if not clean.replace('-', '').replace('_', '').isalnum():
        raise ValueError('External calendar provider name is invalid.')
    return clean


def _external_ref(value: str) -> str:
    clean = (value or '').strip()
    if not clean or len(clean) > 512:
        raise ValueError('External calendar event reference is invalid.')
    if any(ord(char) < 32 for char in clean):
        raise ValueError('External calendar event reference is invalid.')
    return clean
