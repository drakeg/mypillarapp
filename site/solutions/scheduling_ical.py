from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import secrets

import portal_auth
import portal_tenancy
import scheduling_appointments
import scheduling_boundary
import scheduling_calendars
import tenant_auth


MAX_FEED_WINDOW_DAYS = 366


@dataclass(frozen=True)
class CalendarFeedToken:
    id: int
    organization_id: int
    organization_slug: str
    calendar_id: int
    created_by_user_id: int
    token_prefix: str
    created_at: int
    revoked_at: int | None


@dataclass(frozen=True)
class NewCalendarFeedToken:
    metadata: CalendarFeedToken
    token: str


def ensure_schema() -> None:
    scheduling_appointments.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS scheduling_calendar_feed_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                calendar_id INTEGER NOT NULL,
                created_by_user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                token_prefix TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                revoked_at INTEGER,
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(calendar_id)
                    REFERENCES scheduling_calendars(id) ON DELETE CASCADE,
                FOREIGN KEY(created_by_user_id)
                    REFERENCES auth_users(id) ON DELETE RESTRICT
            )
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_scheduling_feed_tokens_calendar
            ON scheduling_calendar_feed_tokens(
                organization_id,calendar_id,revoked_at,id
            )
            '''
        )
        conn.commit()


def render_staff_calendar(
    user_id: int,
    organization_slug: str,
    *,
    calendar_id: int,
    start_at: int,
    end_at: int,
) -> str:
    scope = scheduling_boundary.require(
        user_id, organization_slug, 'view'
    )
    calendar = scheduling_calendars.get_calendar(
        scope.organization_slug, calendar_id
    )
    if calendar is None:
        raise PermissionError('Scheduling calendar access denied.')
    start, end = _window(start_at, end_at)
    appointments = [
        item
        for item in scheduling_appointments.list_appointments(
            scope.organization_slug,
            start_at=start,
            end_at=end,
            include_canceled=True,
        )
        if item.calendar_id == calendar.id
    ]
    return _render(
        scope.organization_slug,
        calendar,
        appointments,
    )


def render_customer_appointment(
    scope: portal_tenancy.CustomerScope,
    appointment_id: int,
) -> str:
    checked = portal_auth.revalidate_customer_scope(scope)
    appointment = scheduling_appointments.get_appointment(
        checked.organization_slug, appointment_id
    )
    if (
        appointment is None
        or appointment.customer_user_id != checked.user_id
    ):
        raise PermissionError(
            'Customer appointment calendar access denied.'
        )
    calendar = scheduling_calendars.get_calendar(
        checked.organization_slug,
        appointment.calendar_id,
    )
    if calendar is None:
        raise PermissionError(
            'Customer appointment calendar is unavailable.'
        )
    return _render(
        checked.organization_slug,
        calendar,
        [appointment],
    )


def create_feed_token(
    user_id: int,
    organization_slug: str,
    *,
    calendar_id: int,
) -> NewCalendarFeedToken:
    scope = scheduling_boundary.require(
        user_id, organization_slug, 'admin'
    )
    calendar = scheduling_calendars.get_calendar(
        scope.organization_slug, calendar_id
    )
    if calendar is None or calendar.status == 'archived':
        raise PermissionError('Scheduling calendar access denied.')
    ensure_schema()

    token = secrets.token_urlsafe(32)
    digest = _hash_token(token)
    prefix = token[:8]
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        cur = conn.execute(
            '''
            INSERT INTO scheduling_calendar_feed_tokens(
                organization_id,calendar_id,created_by_user_id,
                token_hash,token_prefix,created_at,revoked_at
            ) VALUES(?,?,?,?,?,?,NULL)
            ''',
            (
                scope.organization_id,
                calendar.id,
                scope.user_id,
                digest,
                prefix,
                now,
            ),
        )
        conn.commit()
        row = _token_row(
            conn,
            scope.organization_id,
            int(cur.lastrowid),
        )
    return NewCalendarFeedToken(
        metadata=_token_from_row(row),
        token=token,
    )


def revoke_feed_token(
    user_id: int,
    organization_slug: str,
    token_id: int,
) -> CalendarFeedToken:
    scope = scheduling_boundary.require(
        user_id, organization_slug, 'admin'
    )
    ensure_schema()
    with tenant_auth.db() as conn:
        row = _token_row(
            conn,
            scope.organization_id,
            _positive(token_id, 'token_id'),
        )
        if row is None:
            raise PermissionError('Calendar feed token access denied.')
        if row['revoked_at'] is None:
            conn.execute(
                '''
                UPDATE scheduling_calendar_feed_tokens
                SET revoked_at=?
                WHERE organization_id=? AND id=?
                ''',
                (
                    tenant_auth.now(),
                    scope.organization_id,
                    int(token_id),
                ),
            )
            conn.commit()
        row = _token_row(
            conn,
            scope.organization_id,
            int(token_id),
        )
    return _token_from_row(row)


def list_feed_tokens(
    user_id: int,
    organization_slug: str,
    *,
    calendar_id: int,
) -> list[CalendarFeedToken]:
    scope = scheduling_boundary.require(
        user_id, organization_slug, 'admin'
    )
    calendar = scheduling_calendars.get_calendar(
        scope.organization_slug, calendar_id
    )
    if calendar is None:
        raise PermissionError('Scheduling calendar access denied.')
    ensure_schema()
    with tenant_auth.db() as conn:
        rows = conn.execute(
            '''
            SELECT t.*,o.slug AS organization_slug
            FROM scheduling_calendar_feed_tokens t
            JOIN auth_organizations o ON o.id=t.organization_id
            WHERE t.organization_id=? AND t.calendar_id=?
            ORDER BY t.created_at DESC,t.id DESC
            ''',
            (scope.organization_id, calendar.id),
        ).fetchall()
    return [_token_from_row(row) for row in rows]


def render_feed(
    token: str,
    *,
    start_at: int,
    end_at: int,
) -> str:
    clean = (token or '').strip()
    if len(clean) < 32:
        raise PermissionError('Calendar feed token is invalid.')
    start, end = _window(start_at, end_at)
    ensure_schema()
    digest = _hash_token(clean)
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''
            SELECT t.*,o.slug AS organization_slug
            FROM scheduling_calendar_feed_tokens t
            JOIN auth_organizations o ON o.id=t.organization_id
            WHERE t.token_hash=?
              AND t.revoked_at IS NULL
              AND o.status='active'
            LIMIT 1
            ''',
            (digest,),
        ).fetchone()
    if row is None:
        raise PermissionError('Calendar feed token is invalid or revoked.')

    organization_slug = str(row['organization_slug'])
    calendar = scheduling_calendars.get_calendar(
        organization_slug, int(row['calendar_id'])
    )
    if calendar is None or calendar.status == 'archived':
        raise PermissionError('Calendar feed is unavailable.')

    appointments = [
        item
        for item in scheduling_appointments.list_appointments(
            organization_slug,
            start_at=start,
            end_at=end,
            include_canceled=True,
        )
        if item.calendar_id == calendar.id
    ]
    return _render(
        organization_slug,
        calendar,
        appointments,
    )


def _render(
    organization_slug: str,
    calendar: scheduling_calendars.SchedulingCalendar,
    appointments: list[scheduling_appointments.Appointment],
) -> str:
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Mad Mallard Platform//Scheduling//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        f'X-WR-CALNAME:{_escape(calendar.name)}',
        f'X-WR-TIMEZONE:{_escape(calendar.timezone)}',
    ]
    for appointment in appointments:
        service = scheduling_calendars.get_service_type(
            organization_slug, appointment.service_id
        )
        summary = service.name if service else 'Appointment'
        status = (
            'CANCELLED'
            if appointment.status == 'canceled'
            else 'CONFIRMED'
        )
        uid = _uid(
            organization_slug,
            appointment.id,
            appointment.public_ref,
        )
        lines.extend(
            [
                'BEGIN:VEVENT',
                f'UID:{uid}',
                f'DTSTAMP:{_ics_time(appointment.updated_at)}',
                f'DTSTART:{_ics_time(appointment.start_at)}',
                f'DTEND:{_ics_time(appointment.end_at)}',
                f'SUMMARY:{_escape(summary)}',
                f'STATUS:{status}',
                'END:VEVENT',
            ]
        )
    lines.append('END:VCALENDAR')
    return '\r\n'.join(lines) + '\r\n'


def _uid(
    organization_slug: str,
    appointment_id: int,
    public_ref: str,
) -> str:
    material = (
        f'{organization_slug}:{appointment_id}:{public_ref}'
    ).encode('utf-8')
    digest = hashlib.sha256(material).hexdigest()[:32]
    return f'{digest}@scheduling.madmallard.local'


def _ics_time(value: int) -> str:
    return datetime.fromtimestamp(
        int(value), tz=timezone.utc
    ).strftime('%Y%m%dT%H%M%SZ')


def _escape(value: str) -> str:
    clean = str(value or '')
    return (
        clean.replace('\\', '\\\\')
        .replace(';', '\\;')
        .replace(',', '\\,')
        .replace('\r\n', '\\n')
        .replace('\r', '\\n')
        .replace('\n', '\\n')
    )


def _window(start_at: int, end_at: int) -> tuple[int, int]:
    start, end = scheduling_boundary.validate_utc_range(
        start_at, end_at
    )
    if end - start > MAX_FEED_WINDOW_DAYS * 86400:
        raise ValueError(
            f'Calendar feed window cannot exceed '
            f'{MAX_FEED_WINDOW_DAYS} days.'
        )
    return start, end


def _hash_token(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _organization_id(organization_slug: str) -> int:
    clean = (organization_slug or '').strip().lower()
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''SELECT id FROM auth_organizations
               WHERE slug=? AND status='active' LIMIT 1''',
            (clean,),
        ).fetchone()
    if row is None:
        raise PermissionError('Scheduling organization is not active.')
    return int(row['id'])


def _positive(value: int, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f'{label} must be a positive integer.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label} must be a positive integer.') from exc
    if clean <= 0:
        raise ValueError(f'{label} must be a positive integer.')
    return clean


def _token_row(conn, organization_id: int, token_id: int):
    return conn.execute(
        '''
        SELECT t.*,o.slug AS organization_slug
        FROM scheduling_calendar_feed_tokens t
        JOIN auth_organizations o ON o.id=t.organization_id
        WHERE t.organization_id=? AND t.id=?
        LIMIT 1
        ''',
        (organization_id, token_id),
    ).fetchone()


def _token_from_row(row) -> CalendarFeedToken:
    return CalendarFeedToken(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        calendar_id=int(row['calendar_id']),
        created_by_user_id=int(row['created_by_user_id']),
        token_prefix=str(row['token_prefix']),
        created_at=int(row['created_at']),
        revoked_at=(
            int(row['revoked_at'])
            if row['revoked_at'] is not None
            else None
        ),
    )
