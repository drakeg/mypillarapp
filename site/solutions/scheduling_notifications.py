from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import portal_notifications
import scheduling_appointments
import scheduling_calendars
import tenant_auth


KINDS = {'confirmation', 'reminder'}
CHANNELS = {'email', 'in_app'}
STATUSES = {'scheduled', 'queued', 'suppressed', 'canceled'}
DEFAULT_REMINDER_OFFSETS_MINUTES = (1440, 60)
MAX_DUE_LIMIT = 500


@dataclass(frozen=True)
class AppointmentNotification:
    id: int
    organization_id: int
    organization_slug: str
    appointment_id: int
    kind: str
    channel: str
    scheduled_at: int
    status: str
    portal_delivery_id: int | None
    created_at: int
    updated_at: int


@dataclass(frozen=True)
class GuestEmailDue:
    notification_id: int
    organization_slug: str
    appointment_id: int
    booking_reference: str
    guest_name: str
    guest_email: str
    kind: str
    scheduled_at: int
    subject: str
    body: str


def ensure_schema() -> None:
    scheduling_appointments.ensure_schema()
    portal_notifications.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS scheduling_appointment_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                appointment_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                channel TEXT NOT NULL,
                scheduled_at INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'scheduled',
                portal_delivery_id INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(appointment_id,kind,channel,scheduled_at),
                CHECK(kind IN ('confirmation','reminder')),
                CHECK(channel IN ('email','in_app')),
                CHECK(status IN (
                    'scheduled','queued','suppressed','canceled'
                )),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(appointment_id)
                    REFERENCES scheduling_appointments(id) ON DELETE CASCADE,
                FOREIGN KEY(portal_delivery_id)
                    REFERENCES portal_notification_deliveries(id)
                    ON DELETE SET NULL
            )
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_scheduling_notifications_due
            ON scheduling_appointment_notifications(
                organization_id,status,scheduled_at,id
            )
            '''
        )
        conn.commit()


def schedule_initial_notifications(
    organization_slug: str,
    appointment_id: int,
    *,
    now: int | None = None,
    reminder_offsets_minutes: tuple[int, ...] = (
        DEFAULT_REMINDER_OFFSETS_MINUTES
    ),
) -> list[AppointmentNotification]:
    current = tenant_auth.now() if now is None else _epoch(now, 'now')
    appointment = _active_appointment(
        organization_slug, appointment_id
    )
    channels = (
        ('email', 'in_app')
        if appointment.customer_user_id is not None
        else ('email',)
    )

    created: list[AppointmentNotification] = []
    for channel in channels:
        created.append(
            _schedule(
                organization_slug,
                appointment,
                kind='confirmation',
                channel=channel,
                scheduled_at=current,
            )
        )

    for offset in _offsets(reminder_offsets_minutes):
        scheduled_at = appointment.start_at - offset * 60
        if scheduled_at <= current:
            continue
        for channel in channels:
            created.append(
                _schedule(
                    organization_slug,
                    appointment,
                    kind='reminder',
                    channel=channel,
                    scheduled_at=scheduled_at,
                )
            )
    return created


def rebuild_reminders(
    organization_slug: str,
    appointment_id: int,
    *,
    now: int | None = None,
    reminder_offsets_minutes: tuple[int, ...] = (
        DEFAULT_REMINDER_OFFSETS_MINUTES
    ),
) -> list[AppointmentNotification]:
    current = tenant_auth.now() if now is None else _epoch(now, 'now')
    appointment = _active_appointment(
        organization_slug, appointment_id
    )
    _cancel_scheduled(
        organization_slug,
        appointment.id,
        kind='reminder',
    )
    channels = (
        ('email', 'in_app')
        if appointment.customer_user_id is not None
        else ('email',)
    )
    created: list[AppointmentNotification] = []
    for offset in _offsets(reminder_offsets_minutes):
        scheduled_at = appointment.start_at - offset * 60
        if scheduled_at <= current:
            continue
        for channel in channels:
            created.append(
                _schedule(
                    organization_slug,
                    appointment,
                    kind='reminder',
                    channel=channel,
                    scheduled_at=scheduled_at,
                )
            )
    return created


def cancel_scheduled_notifications(
    organization_slug: str,
    appointment_id: int,
) -> None:
    appointment = scheduling_appointments.get_appointment(
        organization_slug, appointment_id
    )
    if appointment is None:
        raise PermissionError('Appointment notification access denied.')
    _cancel_scheduled(
        organization_slug,
        appointment.id,
        kind=None,
    )


def queue_due_authenticated(
    organization_slug: str,
    *,
    now: int | None = None,
    limit: int = 100,
) -> list[AppointmentNotification]:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    current = tenant_auth.now() if now is None else _epoch(now, 'now')
    bounded = _limit(limit)

    with tenant_auth.db() as conn:
        rows = conn.execute(
            '''
            SELECT n.*
            FROM scheduling_appointment_notifications n
            JOIN scheduling_appointments a
              ON a.id=n.appointment_id
             AND a.organization_id=n.organization_id
            WHERE n.organization_id=?
              AND n.status='scheduled'
              AND n.scheduled_at<=?
              AND a.customer_user_id IS NOT NULL
              AND a.status IN ('pending','confirmed')
            ORDER BY n.scheduled_at,n.id
            LIMIT ?
            ''',
            (organization_id, current, bounded),
        ).fetchall()

    processed: list[AppointmentNotification] = []
    for row in rows:
        appointment = scheduling_appointments.get_appointment(
            organization_slug, int(row['appointment_id'])
        )
        if (
            appointment is None
            or appointment.customer_user_id is None
        ):
            continue
        subject, body = _message(
            organization_slug,
            appointment,
            str(row['kind']),
        )
        delivery = portal_notifications.create_delivery(
            organization_slug,
            customer_user_id=appointment.customer_user_id,
            channel=str(row['channel']),
            notification_type='service_notice',
            subject=subject,
            body=body,
            status='queued',
        )
        status = 'queued' if delivery is not None else 'suppressed'
        processed.append(
            _finish(
                organization_slug,
                int(row['id']),
                status=status,
                portal_delivery_id=(
                    delivery.id if delivery is not None else None
                ),
            )
        )
    return processed


def list_due_guest_email(
    organization_slug: str,
    *,
    now: int | None = None,
    limit: int = 100,
) -> list[GuestEmailDue]:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    current = tenant_auth.now() if now is None else _epoch(now, 'now')
    bounded = _limit(limit)
    with tenant_auth.db() as conn:
        rows = conn.execute(
            '''
            SELECT n.id AS notification_id,n.kind,n.scheduled_at,
                   a.id AS appointment_id,a.public_ref,
                   a.guest_name,a.guest_email
            FROM scheduling_appointment_notifications n
            JOIN scheduling_appointments a
              ON a.id=n.appointment_id
             AND a.organization_id=n.organization_id
            WHERE n.organization_id=?
              AND n.status='scheduled'
              AND n.channel='email'
              AND n.scheduled_at<=?
              AND a.customer_user_id IS NULL
              AND trim(a.guest_email)!=''
              AND a.status IN ('pending','confirmed')
            ORDER BY n.scheduled_at,n.id
            LIMIT ?
            ''',
            (organization_id, current, bounded),
        ).fetchall()

    result: list[GuestEmailDue] = []
    for row in rows:
        appointment = scheduling_appointments.get_appointment(
            organization_slug, int(row['appointment_id'])
        )
        if appointment is None:
            continue
        subject, body = _message(
            organization_slug,
            appointment,
            str(row['kind']),
        )
        result.append(
            GuestEmailDue(
                notification_id=int(row['notification_id']),
                organization_slug=organization_slug,
                appointment_id=appointment.id,
                booking_reference=str(row['public_ref'] or ''),
                guest_name=str(row['guest_name'] or ''),
                guest_email=str(row['guest_email'] or ''),
                kind=str(row['kind']),
                scheduled_at=int(row['scheduled_at']),
                subject=subject,
                body=body,
            )
        )
    return result


def mark_guest_email_queued(
    organization_slug: str,
    notification_id: int,
) -> AppointmentNotification:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''
            SELECT n.*
            FROM scheduling_appointment_notifications n
            JOIN scheduling_appointments a
              ON a.id=n.appointment_id
             AND a.organization_id=n.organization_id
            WHERE n.organization_id=?
              AND n.id=?
              AND n.channel='email'
              AND n.status='scheduled'
              AND a.customer_user_id IS NULL
              AND trim(a.guest_email)!=''
            LIMIT 1
            ''',
            (organization_id, _positive(notification_id, 'notification_id')),
        ).fetchone()
    if row is None:
        raise PermissionError('Guest notification access denied.')
    return _finish(
        organization_slug,
        int(row['id']),
        status='queued',
        portal_delivery_id=None,
    )


def list_notifications(
    organization_slug: str,
    appointment_id: int,
) -> list[AppointmentNotification]:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    appointment = scheduling_appointments.get_appointment(
        organization_slug, appointment_id
    )
    if appointment is None:
        return []
    with tenant_auth.db() as conn:
        rows = conn.execute(
            '''
            SELECT n.*,o.slug AS organization_slug
            FROM scheduling_appointment_notifications n
            JOIN auth_organizations o ON o.id=n.organization_id
            WHERE n.organization_id=? AND n.appointment_id=?
            ORDER BY n.scheduled_at,n.id
            ''',
            (organization_id, appointment.id),
        ).fetchall()
    return [_from_row(row) for row in rows]


def _schedule(
    organization_slug: str,
    appointment: scheduling_appointments.Appointment,
    *,
    kind: str,
    channel: str,
    scheduled_at: int,
) -> AppointmentNotification:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    clean_kind = _kind(kind)
    clean_channel = _channel(channel)
    when = _epoch(scheduled_at, 'scheduled_at')
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            INSERT OR IGNORE INTO scheduling_appointment_notifications(
                organization_id,appointment_id,kind,channel,
                scheduled_at,status,portal_delivery_id,
                created_at,updated_at
            ) VALUES(?,?,?,?,?,'scheduled',NULL,?,?)
            ''',
            (
                organization_id,
                appointment.id,
                clean_kind,
                clean_channel,
                when,
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            '''
            SELECT n.*,o.slug AS organization_slug
            FROM scheduling_appointment_notifications n
            JOIN auth_organizations o ON o.id=n.organization_id
            WHERE n.organization_id=?
              AND n.appointment_id=?
              AND n.kind=?
              AND n.channel=?
              AND n.scheduled_at=?
            LIMIT 1
            ''',
            (
                organization_id,
                appointment.id,
                clean_kind,
                clean_channel,
                when,
            ),
        ).fetchone()
    return _from_row(row)


def _cancel_scheduled(
    organization_slug: str,
    appointment_id: int,
    *,
    kind: str | None,
) -> None:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    sql = '''
        UPDATE scheduling_appointment_notifications
        SET status='canceled',updated_at=?
        WHERE organization_id=?
          AND appointment_id=?
          AND status='scheduled'
    '''
    params: list[object] = [
        tenant_auth.now(),
        organization_id,
        int(appointment_id),
    ]
    if kind is not None:
        sql += ' AND kind=?'
        params.append(_kind(kind))
    with tenant_auth.db() as conn:
        conn.execute(sql, params)
        conn.commit()


def _finish(
    organization_slug: str,
    notification_id: int,
    *,
    status: str,
    portal_delivery_id: int | None,
) -> AppointmentNotification:
    if status not in {'queued', 'suppressed'}:
        raise ValueError('Notification completion status is invalid.')
    organization_id = _organization_id(organization_slug)
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            UPDATE scheduling_appointment_notifications
            SET status=?,portal_delivery_id=?,updated_at=?
            WHERE organization_id=? AND id=? AND status='scheduled'
            ''',
            (
                status,
                portal_delivery_id,
                tenant_auth.now(),
                organization_id,
                notification_id,
            ),
        )
        row = conn.execute(
            '''
            SELECT n.*,o.slug AS organization_slug
            FROM scheduling_appointment_notifications n
            JOIN auth_organizations o ON o.id=n.organization_id
            WHERE n.organization_id=? AND n.id=?
            LIMIT 1
            ''',
            (organization_id, notification_id),
        ).fetchone()
        conn.commit()
    if row is None:
        raise PermissionError('Notification access denied.')
    return _from_row(row)


def _active_appointment(
    organization_slug: str,
    appointment_id: int,
) -> scheduling_appointments.Appointment:
    appointment = scheduling_appointments.get_appointment(
        organization_slug, appointment_id
    )
    if (
        appointment is None
        or appointment.status not in {'pending', 'confirmed'}
    ):
        raise ValueError(
            'Only pending/confirmed appointments may schedule notices.'
        )
    return appointment


def _message(
    organization_slug: str,
    appointment: scheduling_appointments.Appointment,
    kind: str,
) -> tuple[str, str]:
    service = scheduling_calendars.get_service_type(
        organization_slug, appointment.service_id
    )
    calendar = scheduling_calendars.get_calendar(
        organization_slug, appointment.calendar_id
    )
    service_name = service.name if service else 'Appointment'
    timezone_name = calendar.timezone if calendar else 'UTC'
    local = (
        datetime.fromtimestamp(
            appointment.start_at, tz=timezone.utc
        )
        .astimezone(
            __import__('zoneinfo').ZoneInfo(timezone_name)
        )
        .strftime('%Y-%m-%d %H:%M %Z')
    )
    if kind == 'confirmation':
        return (
            f'{service_name} booking confirmed',
            f'Your {service_name} is scheduled for {local}.',
        )
    return (
        f'{service_name} reminder',
        f'Reminder: your {service_name} is scheduled for {local}.',
    )


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


def _kind(value: str) -> str:
    clean = (value or '').strip().lower()
    if clean not in KINDS:
        raise ValueError(f'Unknown appointment notification kind: {clean}')
    return clean


def _channel(value: str) -> str:
    clean = (value or '').strip().lower()
    if clean not in CHANNELS:
        raise ValueError(f'Unknown appointment notification channel: {clean}')
    return clean


def _offsets(values: tuple[int, ...]) -> tuple[int, ...]:
    clean: list[int] = []
    for value in values:
        if isinstance(value, bool):
            raise ValueError('Reminder offsets must be positive minutes.')
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                'Reminder offsets must be positive minutes.'
            ) from exc
        if parsed <= 0 or parsed > 43_200:
            raise ValueError(
                'Reminder offsets must be 1 to 43200 minutes.'
            )
        if parsed not in clean:
            clean.append(parsed)
    return tuple(sorted(clean, reverse=True))


def _limit(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError('Notification limit must be an integer.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Notification limit must be an integer.') from exc
    if clean < 1:
        raise ValueError('Notification limit must be at least 1.')
    return min(clean, MAX_DUE_LIMIT)


def _epoch(value: int, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f'{label} must be a UTC epoch integer.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label} must be a UTC epoch integer.') from exc
    if clean < 0:
        raise ValueError(f'{label} must be a UTC epoch integer.')
    return clean


def _positive(value: int, label: str) -> int:
    clean = _epoch(value, label)
    if clean <= 0:
        raise ValueError(f'{label} must be positive.')
    return clean


def _from_row(row) -> AppointmentNotification:
    return AppointmentNotification(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        appointment_id=int(row['appointment_id']),
        kind=str(row['kind']),
        channel=str(row['channel']),
        scheduled_at=int(row['scheduled_at']),
        status=str(row['status']),
        portal_delivery_id=(
            int(row['portal_delivery_id'])
            if row['portal_delivery_id'] is not None
            else None
        ),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
