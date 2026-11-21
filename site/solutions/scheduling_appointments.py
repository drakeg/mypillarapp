from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3

import crm_contacts

import scheduling_availability
import scheduling_boundary
import scheduling_calendars
import tenant_auth


APPOINTMENT_STATUSES = {
    'pending',
    'confirmed',
    'canceled',
    'completed',
    'no_show',
}
BLOCKING_STATUSES = {'pending', 'confirmed'}
_PUBLIC_REF_RE = re.compile(r'^[A-Za-z0-9_-]{16,128}$')
_EMAIL_RE = re.compile(r'^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$')


class AppointmentConflictError(ValueError):
    pass


_TRANSITIONS = {
    'pending': {'confirmed', 'canceled'},
    'confirmed': {'canceled', 'completed', 'no_show'},
    'canceled': set(),
    'completed': set(),
    'no_show': set(),
}

@dataclass(frozen=True)
class Appointment:
    id: int
    organization_id: int
    organization_slug: str
    calendar_id: int
    service_id: int
    resource_id: int
    customer_user_id: int | None
    crm_contact_id: int | None
    public_ref: str
    guest_name: str
    guest_email: str
    guest_phone: str
    status: str
    start_at: int
    end_at: int
    block_start_at: int
    block_end_at: int
    duration_minutes: int
    buffer_before_minutes: int
    buffer_after_minutes: int
    created_by_user_id: int | None
    created_at: int
    updated_at: int


@dataclass(frozen=True)
class AppointmentTransition:
    id: int
    appointment_id: int
    organization_id: int
    from_status: str
    to_status: str
    actor_user_id: int | None
    reason: str
    created_at: int


def ensure_schema() -> None:
    scheduling_availability.ensure_schema()
    crm_contacts.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS scheduling_appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                calendar_id INTEGER NOT NULL,
                service_id INTEGER NOT NULL,
                resource_id INTEGER NOT NULL,
                customer_user_id INTEGER,
                crm_contact_id INTEGER,
                public_ref TEXT,
                guest_name TEXT NOT NULL DEFAULT '',
                guest_email TEXT NOT NULL DEFAULT '',
                guest_phone TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                start_at INTEGER NOT NULL,
                end_at INTEGER NOT NULL,
                block_start_at INTEGER NOT NULL,
                block_end_at INTEGER NOT NULL,
                duration_minutes INTEGER NOT NULL,
                buffer_before_minutes INTEGER NOT NULL,
                buffer_after_minutes INTEGER NOT NULL,
                created_by_user_id INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                CHECK(status IN (
                    'pending','confirmed','canceled','completed','no_show'
                )),
                CHECK(end_at > start_at),
                CHECK(block_end_at > block_start_at),
                CHECK(duration_minutes BETWEEN 5 AND 1440),
                CHECK(buffer_before_minutes BETWEEN 0 AND 1440),
                CHECK(buffer_after_minutes BETWEEN 0 AND 1440),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(calendar_id)
                    REFERENCES scheduling_calendars(id) ON DELETE RESTRICT,
                FOREIGN KEY(service_id)
                    REFERENCES scheduling_service_types(id) ON DELETE RESTRICT,
                FOREIGN KEY(resource_id)
                    REFERENCES scheduling_resources(id) ON DELETE RESTRICT,
                FOREIGN KEY(customer_user_id)
                    REFERENCES auth_users(id) ON DELETE SET NULL,
                FOREIGN KEY(crm_contact_id)
                    REFERENCES crm_v2_contacts(id) ON DELETE SET NULL,
                FOREIGN KEY(created_by_user_id)
                    REFERENCES auth_users(id) ON DELETE SET NULL
            )
            '''
        )
        columns = {
            str(row['name'])
            for row in conn.execute(
                'PRAGMA table_info(scheduling_appointments)'
            ).fetchall()
        }
        if 'public_ref' not in columns:
            conn.execute(
                'ALTER TABLE scheduling_appointments '
                'ADD COLUMN public_ref TEXT'
            )
        if 'guest_name' not in columns:
            conn.execute(
                "ALTER TABLE scheduling_appointments "
                "ADD COLUMN guest_name TEXT NOT NULL DEFAULT ''"
            )
        if 'guest_email' not in columns:
            conn.execute(
                "ALTER TABLE scheduling_appointments "
                "ADD COLUMN guest_email TEXT NOT NULL DEFAULT ''"
            )
        if 'guest_phone' not in columns:
            conn.execute(
                "ALTER TABLE scheduling_appointments "
                "ADD COLUMN guest_phone TEXT NOT NULL DEFAULT ''"
            )
        conn.execute(
            '''
            CREATE UNIQUE INDEX IF NOT EXISTS
                idx_scheduling_appointments_public_ref
            ON scheduling_appointments(public_ref)
            WHERE public_ref IS NOT NULL
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_scheduling_appointments_resource
            ON scheduling_appointments(
                organization_id,resource_id,start_at,end_at,status,id
            )
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_scheduling_appointments_customer
            ON scheduling_appointments(
                organization_id,customer_user_id,start_at,id
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS scheduling_appointment_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                appointment_id INTEGER NOT NULL,
                organization_id INTEGER NOT NULL,
                from_status TEXT NOT NULL,
                to_status TEXT NOT NULL,
                actor_user_id INTEGER,
                reason TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                FOREIGN KEY(appointment_id)
                    REFERENCES scheduling_appointments(id) ON DELETE CASCADE,
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(actor_user_id)
                    REFERENCES auth_users(id) ON DELETE SET NULL
            )
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_scheduling_appointment_transitions
            ON scheduling_appointment_transitions(
                organization_id,appointment_id,created_at,id
            )
            '''
        )
        conn.commit()


def create_appointment(
    organization_slug: str,
    *,
    service_id: int,
    resource_id: int,
    start_at: int,
    status: str = 'confirmed',
    customer_user_id: int | None = None,
    crm_contact_id: int | None = None,
    public_ref: str | None = None,
    guest_name: str = '',
    guest_email: str = '',
    guest_phone: str = '',
    actor_user_id: int | None = None,
    reason: str = '',
) -> Appointment:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    service = scheduling_calendars.get_service_type(
        organization_slug, service_id
    )
    resource = scheduling_availability.get_resource(
        organization_slug, resource_id
    )
    if (
        service is None
        or service.status == 'archived'
        or resource is None
        or resource.status != 'active'
    ):
        raise PermissionError(
            'Appointment service/resource is unavailable.'
        )
    if service.calendar_id != resource.calendar_id:
        raise PermissionError(
            'Appointment service/resource must share a calendar.'
        )
    allowed_resources = scheduling_availability.list_service_resources(
        organization_slug, service.id
    )
    if resource.id not in {item.id for item in allowed_resources}:
        raise PermissionError(
            'Resource is not assigned to this service.'
        )

    clean_status = _status(status)
    if clean_status not in {'pending', 'confirmed'}:
        raise ValueError(
            'New appointments must start pending or confirmed.'
        )

    clean_customer = scheduling_boundary.require_customer_user(
        organization_slug, customer_user_id
    )
    clean_contact = scheduling_boundary.require_contact(
        organization_slug, crm_contact_id
    )
    clean_actor = _actor_user(
        organization_slug, actor_user_id
    )
    clean_public_ref = _public_ref(public_ref)
    clean_guest_name = _guest_name(guest_name)
    clean_guest_email = _guest_email(guest_email)
    clean_guest_phone = _guest_phone(guest_phone)

    start = _epoch(start_at, 'start_at')
    duration = int(service.duration_minutes)
    before = int(service.buffer_before_minutes)
    after = int(service.buffer_after_minutes)
    end = start + (duration * 60)
    block_start = start - (before * 60)
    block_end = end + (after * 60)
    if block_start < 0:
        raise ValueError(
            'Appointment buffer would precede the UTC epoch.'
        )

    now = tenant_auth.now()
    clean_reason = _reason(reason)
    with tenant_auth.db() as conn:
        conn.commit()
        conn.execute('BEGIN IMMEDIATE')
        _assert_resource_ownership(
            conn,
            organization_id,
            service.id,
            resource.id,
            service.calendar_id,
        )
        _assert_no_conflict(
            conn,
            organization_id,
            resource.id,
            block_start,
            block_end,
        )
        cur = conn.execute(
            '''
            INSERT INTO scheduling_appointments(
                organization_id,calendar_id,service_id,resource_id,
                customer_user_id,crm_contact_id,public_ref,
                guest_name,guest_email,guest_phone,status,start_at,end_at,
                block_start_at,block_end_at,duration_minutes,
                buffer_before_minutes,buffer_after_minutes,
                created_by_user_id,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''',
            (
                organization_id,
                service.calendar_id,
                service.id,
                resource.id,
                clean_customer,
                clean_contact,
                clean_public_ref,
                clean_guest_name,
                clean_guest_email,
                clean_guest_phone,
                clean_status,
                start,
                end,
                block_start,
                block_end,
                duration,
                before,
                after,
                clean_actor,
                now,
                now,
            ),
        )
        appointment_id = int(cur.lastrowid)
        conn.execute(
            '''
            INSERT INTO scheduling_appointment_transitions(
                appointment_id,organization_id,from_status,to_status,
                actor_user_id,reason,created_at
            ) VALUES(?,?,'new',?,?,?,?)
            ''',
            (
                appointment_id,
                organization_id,
                clean_status,
                clean_actor,
                clean_reason,
                now,
            ),
        )
        conn.commit()
        row = _appointment_row(
            conn, organization_id, appointment_id
        )
    return _appointment_from_row(row)


def get_appointment(
    organization_slug: str,
    appointment_id: int,
) -> Appointment | None:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    with tenant_auth.db() as conn:
        row = _appointment_row(
            conn,
            organization_id,
            _positive_int(appointment_id, 'appointment_id'),
        )
    return _appointment_from_row(row) if row else None


def list_appointments(
    organization_slug: str,
    *,
    resource_id: int | None = None,
    customer_user_id: int | None = None,
    start_at: int | None = None,
    end_at: int | None = None,
    include_canceled: bool = False,
) -> list[Appointment]:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    sql = '''
        SELECT a.*,o.slug AS organization_slug
        FROM scheduling_appointments a
        JOIN auth_organizations o ON o.id=a.organization_id
        WHERE a.organization_id=?
    '''
    params: list[object] = [organization_id]
    if resource_id is not None:
        resource = scheduling_availability.get_resource(
            organization_slug, resource_id
        )
        if resource is None:
            return []
        sql += ' AND a.resource_id=?'
        params.append(resource.id)
    if customer_user_id is not None:
        customer_id = scheduling_boundary.require_customer_user(
            organization_slug, customer_user_id
        )
        sql += ' AND a.customer_user_id=?'
        params.append(customer_id)
    if start_at is not None and end_at is not None:
        start, end = scheduling_boundary.validate_utc_range(
            start_at, end_at
        )
        sql += ' AND a.start_at < ? AND a.end_at > ?'
        params.extend([end, start])
    elif start_at is not None or end_at is not None:
        raise ValueError(
            'Appointment time filtering requires start_at and end_at.'
        )
    if not include_canceled:
        sql += " AND a.status!='canceled'"
    sql += ' ORDER BY a.start_at,a.id'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_appointment_from_row(row) for row in rows]


def transition_appointment(
    organization_slug: str,
    appointment_id: int,
    *,
    to_status: str,
    actor_user_id: int | None = None,
    reason: str = '',
) -> Appointment:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    appointment_id = _positive_int(
        appointment_id, 'appointment_id'
    )
    clean_status = _status(to_status)
    clean_actor = _actor_user(
        organization_slug, actor_user_id
    )
    clean_reason = _reason(reason)
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        conn.commit()
        conn.execute('BEGIN IMMEDIATE')
        row = _appointment_row(
            conn, organization_id, appointment_id
        )
        if row is None:
            conn.rollback()
            raise ValueError('Appointment not found.')
        current = str(row['status'])
        if clean_status == current:
            conn.rollback()
            return _appointment_from_row(row)
        if clean_status not in _TRANSITIONS.get(current, set()):
            conn.rollback()
            raise ValueError(
                f'Invalid appointment transition: '
                f'{current} -> {clean_status}.'
            )
        conn.execute(
            '''
            UPDATE scheduling_appointments
            SET status=?,updated_at=?
            WHERE organization_id=? AND id=?
            ''',
            (
                clean_status,
                now,
                organization_id,
                appointment_id,
            ),
        )
        conn.execute(
            '''
            INSERT INTO scheduling_appointment_transitions(
                appointment_id,organization_id,from_status,to_status,
                actor_user_id,reason,created_at
            ) VALUES(?,?,?,?,?,?,?)
            ''',
            (
                appointment_id,
                organization_id,
                current,
                clean_status,
                clean_actor,
                clean_reason,
                now,
            ),
        )
        conn.commit()
        updated = _appointment_row(
            conn, organization_id, appointment_id
        )
    return _appointment_from_row(updated)


def list_transitions(
    organization_slug: str,
    appointment_id: int,
) -> list[AppointmentTransition]:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    appointment = get_appointment(
        organization_slug, appointment_id
    )
    if appointment is None:
        return []
    with tenant_auth.db() as conn:
        rows = conn.execute(
            '''
            SELECT *
            FROM scheduling_appointment_transitions
            WHERE organization_id=? AND appointment_id=?
            ORDER BY created_at,id
            ''',
            (organization_id, appointment.id),
        ).fetchall()
    return [_transition_from_row(row) for row in rows]



def list_blocking_intervals(
    organization_slug: str,
    resource_id: int,
    *,
    start_at: int,
    end_at: int,
) -> list[tuple[int, int]]:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    resource = scheduling_availability.get_resource(
        organization_slug, resource_id
    )
    if resource is None or resource.status != 'active':
        return []
    start, end = scheduling_boundary.validate_utc_range(
        start_at, end_at
    )
    with tenant_auth.db() as conn:
        rows = conn.execute(
            """
            SELECT block_start_at,block_end_at
            FROM scheduling_appointments
            WHERE organization_id=?
              AND resource_id=?
              AND status IN ('pending','confirmed')
              AND block_start_at < ?
              AND block_end_at > ?
            ORDER BY block_start_at,block_end_at,id
            """,
            (organization_id, resource.id, end, start),
        ).fetchall()
    return [
        (int(row['block_start_at']), int(row['block_end_at']))
        for row in rows
    ]

def _assert_resource_ownership(
    conn,
    organization_id: int,
    service_id: int,
    resource_id: int,
    calendar_id: int,
) -> None:
    row = conn.execute(
        '''
        SELECT 1
        FROM scheduling_service_resources sr
        JOIN scheduling_service_types s
          ON s.id=sr.service_id
         AND s.organization_id=sr.organization_id
        JOIN scheduling_resources r
          ON r.id=sr.resource_id
         AND r.organization_id=sr.organization_id
        WHERE sr.organization_id=?
          AND sr.service_id=?
          AND sr.resource_id=?
          AND s.calendar_id=?
          AND r.calendar_id=?
          AND s.status!='archived'
          AND r.status='active'
        LIMIT 1
        ''',
        (
            organization_id,
            service_id,
            resource_id,
            calendar_id,
            calendar_id,
        ),
    ).fetchone()
    if row is None:
        raise PermissionError(
            'Appointment resource ownership changed.'
        )


def _assert_no_conflict(
    conn,
    organization_id: int,
    resource_id: int,
    block_start: int,
    block_end: int,
) -> None:
    row = conn.execute(
        '''
        SELECT id
        FROM scheduling_appointments
        WHERE organization_id=?
          AND resource_id=?
          AND status IN ('pending','confirmed')
          AND block_start_at < ?
          AND block_end_at > ?
        LIMIT 1
        ''',
        (
            organization_id,
            resource_id,
            block_end,
            block_start,
        ),
    ).fetchone()
    if row is not None:
        raise AppointmentConflictError(
            'Appointment conflicts with an existing resource booking.'
        )


def _actor_user(
    organization_slug: str,
    actor_user_id: int | None,
) -> int | None:
    if actor_user_id is None:
        return None
    access = scheduling_boundary.require(
        actor_user_id, organization_slug, 'manage'
    )
    return access.user_id


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



def _public_ref(value: str | None) -> str | None:
    if value is None:
        return None
    clean = value.strip()
    if not _PUBLIC_REF_RE.fullmatch(clean):
        raise ValueError('Public booking reference is invalid.')
    return clean


def _guest_name(value: str) -> str:
    clean = (value or '').strip()
    if len(clean) > 200:
        raise ValueError('Guest name must be 200 characters or fewer.')
    return clean


def _guest_email(value: str) -> str:
    clean = (value or '').strip().lower()
    if not clean:
        return ''
    if len(clean) > 320 or not _EMAIL_RE.fullmatch(clean):
        raise ValueError('Guest email is invalid.')
    return clean


def _guest_phone(value: str) -> str:
    clean = (value or '').strip()
    if not clean:
        return ''
    digits = ''.join(ch for ch in clean if ch.isdigit())
    if len(digits) < 7 or len(digits) > 15:
        raise ValueError('Guest phone must contain 7 to 15 digits.')
    return ('+' if clean.startswith('+') else '') + digits


def _status(value: str) -> str:
    clean = (value or '').strip().lower()
    if clean not in APPOINTMENT_STATUSES:
        raise ValueError(
            f'Unknown appointment status: {clean}'
        )
    return clean


def _reason(value: str) -> str:
    clean = (value or '').strip()
    if len(clean) > 500:
        raise ValueError(
            'Appointment transition reason must be 500 characters or fewer.'
        )
    return clean


def _epoch(value: int, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f'{label} must be an integer UTC epoch.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f'{label} must be an integer UTC epoch.'
        ) from exc
    if clean < 0:
        raise ValueError(
            f'{label} must be an integer UTC epoch.'
        )
    return clean


def _positive_int(value: int, label: str) -> int:
    clean = _epoch(value, label)
    if clean <= 0:
        raise ValueError(f'{label} must be a positive integer.')
    return clean


def _appointment_row(
    conn,
    organization_id: int,
    appointment_id: int,
):
    return conn.execute(
        '''
        SELECT a.*,o.slug AS organization_slug
        FROM scheduling_appointments a
        JOIN auth_organizations o ON o.id=a.organization_id
        WHERE a.organization_id=? AND a.id=?
        LIMIT 1
        ''',
        (organization_id, appointment_id),
    ).fetchone()


def _appointment_from_row(row) -> Appointment:
    return Appointment(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        calendar_id=int(row['calendar_id']),
        service_id=int(row['service_id']),
        resource_id=int(row['resource_id']),
        customer_user_id=(
            int(row['customer_user_id'])
            if row['customer_user_id'] is not None
            else None
        ),
        crm_contact_id=(
            int(row['crm_contact_id'])
            if row['crm_contact_id'] is not None
            else None
        ),
        public_ref=str(row['public_ref'] or ''),
        guest_name=str(row['guest_name'] or ''),
        guest_email=str(row['guest_email'] or ''),
        guest_phone=str(row['guest_phone'] or ''),
        status=str(row['status']),
        start_at=int(row['start_at']),
        end_at=int(row['end_at']),
        block_start_at=int(row['block_start_at']),
        block_end_at=int(row['block_end_at']),
        duration_minutes=int(row['duration_minutes']),
        buffer_before_minutes=int(row['buffer_before_minutes']),
        buffer_after_minutes=int(row['buffer_after_minutes']),
        created_by_user_id=(
            int(row['created_by_user_id'])
            if row['created_by_user_id'] is not None
            else None
        ),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )


def _transition_from_row(row) -> AppointmentTransition:
    return AppointmentTransition(
        id=int(row['id']),
        appointment_id=int(row['appointment_id']),
        organization_id=int(row['organization_id']),
        from_status=str(row['from_status']),
        to_status=str(row['to_status']),
        actor_user_id=(
            int(row['actor_user_id'])
            if row['actor_user_id'] is not None
            else None
        ),
        reason=str(row['reason']),
        created_at=int(row['created_at']),
    )
)
_EMAIL_RE = re.compile(r'^[^\\s@]+@[^\\s@]+\\.[^\\s@]+_TRANSITIONS = {
    'pending': {'confirmed', 'canceled'},
    'confirmed': {'canceled', 'completed', 'no_show'},
    'canceled': set(),
    'completed': set(),
    'no_show': set(),
}


@dataclass(frozen=True)
class Appointment:
    id: int
    organization_id: int
    organization_slug: str
    calendar_id: int
    service_id: int
    resource_id: int
    customer_user_id: int | None
    crm_contact_id: int | None
    status: str
    start_at: int
    end_at: int
    block_start_at: int
    block_end_at: int
    duration_minutes: int
    buffer_before_minutes: int
    buffer_after_minutes: int
    created_by_user_id: int | None
    created_at: int
    updated_at: int


@dataclass(frozen=True)
class AppointmentTransition:
    id: int
    appointment_id: int
    organization_id: int
    from_status: str
    to_status: str
    actor_user_id: int | None
    reason: str
    created_at: int


def ensure_schema() -> None:
    scheduling_availability.ensure_schema()
    crm_contacts.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS scheduling_appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                calendar_id INTEGER NOT NULL,
                service_id INTEGER NOT NULL,
                resource_id INTEGER NOT NULL,
                customer_user_id INTEGER,
                crm_contact_id INTEGER,
                status TEXT NOT NULL,
                start_at INTEGER NOT NULL,
                end_at INTEGER NOT NULL,
                block_start_at INTEGER NOT NULL,
                block_end_at INTEGER NOT NULL,
                duration_minutes INTEGER NOT NULL,
                buffer_before_minutes INTEGER NOT NULL,
                buffer_after_minutes INTEGER NOT NULL,
                created_by_user_id INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                CHECK(status IN (
                    'pending','confirmed','canceled','completed','no_show'
                )),
                CHECK(end_at > start_at),
                CHECK(block_end_at > block_start_at),
                CHECK(duration_minutes BETWEEN 5 AND 1440),
                CHECK(buffer_before_minutes BETWEEN 0 AND 1440),
                CHECK(buffer_after_minutes BETWEEN 0 AND 1440),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(calendar_id)
                    REFERENCES scheduling_calendars(id) ON DELETE RESTRICT,
                FOREIGN KEY(service_id)
                    REFERENCES scheduling_service_types(id) ON DELETE RESTRICT,
                FOREIGN KEY(resource_id)
                    REFERENCES scheduling_resources(id) ON DELETE RESTRICT,
                FOREIGN KEY(customer_user_id)
                    REFERENCES auth_users(id) ON DELETE SET NULL,
                FOREIGN KEY(crm_contact_id)
                    REFERENCES crm_v2_contacts(id) ON DELETE SET NULL,
                FOREIGN KEY(created_by_user_id)
                    REFERENCES auth_users(id) ON DELETE SET NULL
            )
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_scheduling_appointments_resource
            ON scheduling_appointments(
                organization_id,resource_id,start_at,end_at,status,id
            )
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_scheduling_appointments_customer
            ON scheduling_appointments(
                organization_id,customer_user_id,start_at,id
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS scheduling_appointment_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                appointment_id INTEGER NOT NULL,
                organization_id INTEGER NOT NULL,
                from_status TEXT NOT NULL,
                to_status TEXT NOT NULL,
                actor_user_id INTEGER,
                reason TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                FOREIGN KEY(appointment_id)
                    REFERENCES scheduling_appointments(id) ON DELETE CASCADE,
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(actor_user_id)
                    REFERENCES auth_users(id) ON DELETE SET NULL
            )
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_scheduling_appointment_transitions
            ON scheduling_appointment_transitions(
                organization_id,appointment_id,created_at,id
            )
            '''
        )
        conn.commit()


def create_appointment(
    organization_slug: str,
    *,
    service_id: int,
    resource_id: int,
    start_at: int,
    status: str = 'confirmed',
    customer_user_id: int | None = None,
    crm_contact_id: int | None = None,
    actor_user_id: int | None = None,
    reason: str = '',
) -> Appointment:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    service = scheduling_calendars.get_service_type(
        organization_slug, service_id
    )
    resource = scheduling_availability.get_resource(
        organization_slug, resource_id
    )
    if (
        service is None
        or service.status == 'archived'
        or resource is None
        or resource.status != 'active'
    ):
        raise PermissionError(
            'Appointment service/resource is unavailable.'
        )
    if service.calendar_id != resource.calendar_id:
        raise PermissionError(
            'Appointment service/resource must share a calendar.'
        )
    allowed_resources = scheduling_availability.list_service_resources(
        organization_slug, service.id
    )
    if resource.id not in {item.id for item in allowed_resources}:
        raise PermissionError(
            'Resource is not assigned to this service.'
        )

    clean_status = _status(status)
    if clean_status not in {'pending', 'confirmed'}:
        raise ValueError(
            'New appointments must start pending or confirmed.'
        )

    clean_customer = scheduling_boundary.require_customer_user(
        organization_slug, customer_user_id
    )
    clean_contact = scheduling_boundary.require_contact(
        organization_slug, crm_contact_id
    )
    clean_actor = _actor_user(
        organization_slug, actor_user_id
    )

    start = _epoch(start_at, 'start_at')
    duration = int(service.duration_minutes)
    before = int(service.buffer_before_minutes)
    after = int(service.buffer_after_minutes)
    end = start + (duration * 60)
    block_start = start - (before * 60)
    block_end = end + (after * 60)
    if block_start < 0:
        raise ValueError(
            'Appointment buffer would precede the UTC epoch.'
        )

    now = tenant_auth.now()
    clean_reason = _reason(reason)
    with tenant_auth.db() as conn:
        conn.commit()
        conn.execute('BEGIN IMMEDIATE')
        _assert_resource_ownership(
            conn,
            organization_id,
            service.id,
            resource.id,
            service.calendar_id,
        )
        _assert_no_conflict(
            conn,
            organization_id,
            resource.id,
            block_start,
            block_end,
        )
        cur = conn.execute(
            '''
            INSERT INTO scheduling_appointments(
                organization_id,calendar_id,service_id,resource_id,
                customer_user_id,crm_contact_id,status,start_at,end_at,
                block_start_at,block_end_at,duration_minutes,
                buffer_before_minutes,buffer_after_minutes,
                created_by_user_id,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''',
            (
                organization_id,
                service.calendar_id,
                service.id,
                resource.id,
                clean_customer,
                clean_contact,
                clean_status,
                start,
                end,
                block_start,
                block_end,
                duration,
                before,
                after,
                clean_actor,
                now,
                now,
            ),
        )
        appointment_id = int(cur.lastrowid)
        conn.execute(
            '''
            INSERT INTO scheduling_appointment_transitions(
                appointment_id,organization_id,from_status,to_status,
                actor_user_id,reason,created_at
            ) VALUES(?,?,'new',?,?,?,?)
            ''',
            (
                appointment_id,
                organization_id,
                clean_status,
                clean_actor,
                clean_reason,
                now,
            ),
        )
        conn.commit()
        row = _appointment_row(
            conn, organization_id, appointment_id
        )
    return _appointment_from_row(row)


def get_appointment(
    organization_slug: str,
    appointment_id: int,
) -> Appointment | None:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    with tenant_auth.db() as conn:
        row = _appointment_row(
            conn,
            organization_id,
            _positive_int(appointment_id, 'appointment_id'),
        )
    return _appointment_from_row(row) if row else None


def list_appointments(
    organization_slug: str,
    *,
    resource_id: int | None = None,
    customer_user_id: int | None = None,
    start_at: int | None = None,
    end_at: int | None = None,
    include_canceled: bool = False,
) -> list[Appointment]:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    sql = '''
        SELECT a.*,o.slug AS organization_slug
        FROM scheduling_appointments a
        JOIN auth_organizations o ON o.id=a.organization_id
        WHERE a.organization_id=?
    '''
    params: list[object] = [organization_id]
    if resource_id is not None:
        resource = scheduling_availability.get_resource(
            organization_slug, resource_id
        )
        if resource is None:
            return []
        sql += ' AND a.resource_id=?'
        params.append(resource.id)
    if customer_user_id is not None:
        customer_id = scheduling_boundary.require_customer_user(
            organization_slug, customer_user_id
        )
        sql += ' AND a.customer_user_id=?'
        params.append(customer_id)
    if start_at is not None and end_at is not None:
        start, end = scheduling_boundary.validate_utc_range(
            start_at, end_at
        )
        sql += ' AND a.start_at < ? AND a.end_at > ?'
        params.extend([end, start])
    elif start_at is not None or end_at is not None:
        raise ValueError(
            'Appointment time filtering requires start_at and end_at.'
        )
    if not include_canceled:
        sql += " AND a.status!='canceled'"
    sql += ' ORDER BY a.start_at,a.id'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_appointment_from_row(row) for row in rows]


def transition_appointment(
    organization_slug: str,
    appointment_id: int,
    *,
    to_status: str,
    actor_user_id: int | None = None,
    reason: str = '',
) -> Appointment:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    appointment_id = _positive_int(
        appointment_id, 'appointment_id'
    )
    clean_status = _status(to_status)
    clean_actor = _actor_user(
        organization_slug, actor_user_id
    )
    clean_reason = _reason(reason)
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        conn.commit()
        conn.execute('BEGIN IMMEDIATE')
        row = _appointment_row(
            conn, organization_id, appointment_id
        )
        if row is None:
            conn.rollback()
            raise ValueError('Appointment not found.')
        current = str(row['status'])
        if clean_status == current:
            conn.rollback()
            return _appointment_from_row(row)
        if clean_status not in _TRANSITIONS.get(current, set()):
            conn.rollback()
            raise ValueError(
                f'Invalid appointment transition: '
                f'{current} -> {clean_status}.'
            )
        conn.execute(
            '''
            UPDATE scheduling_appointments
            SET status=?,updated_at=?
            WHERE organization_id=? AND id=?
            ''',
            (
                clean_status,
                now,
                organization_id,
                appointment_id,
            ),
        )
        conn.execute(
            '''
            INSERT INTO scheduling_appointment_transitions(
                appointment_id,organization_id,from_status,to_status,
                actor_user_id,reason,created_at
            ) VALUES(?,?,?,?,?,?,?)
            ''',
            (
                appointment_id,
                organization_id,
                current,
                clean_status,
                clean_actor,
                clean_reason,
                now,
            ),
        )
        conn.commit()
        updated = _appointment_row(
            conn, organization_id, appointment_id
        )
    return _appointment_from_row(updated)


def list_transitions(
    organization_slug: str,
    appointment_id: int,
) -> list[AppointmentTransition]:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    appointment = get_appointment(
        organization_slug, appointment_id
    )
    if appointment is None:
        return []
    with tenant_auth.db() as conn:
        rows = conn.execute(
            '''
            SELECT *
            FROM scheduling_appointment_transitions
            WHERE organization_id=? AND appointment_id=?
            ORDER BY created_at,id
            ''',
            (organization_id, appointment.id),
        ).fetchall()
    return [_transition_from_row(row) for row in rows]



def list_blocking_intervals(
    organization_slug: str,
    resource_id: int,
    *,
    start_at: int,
    end_at: int,
) -> list[tuple[int, int]]:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    resource = scheduling_availability.get_resource(
        organization_slug, resource_id
    )
    if resource is None or resource.status != 'active':
        return []
    start, end = scheduling_boundary.validate_utc_range(
        start_at, end_at
    )
    with tenant_auth.db() as conn:
        rows = conn.execute(
            """
            SELECT block_start_at,block_end_at
            FROM scheduling_appointments
            WHERE organization_id=?
              AND resource_id=?
              AND status IN ('pending','confirmed')
              AND block_start_at < ?
              AND block_end_at > ?
            ORDER BY block_start_at,block_end_at,id
            """,
            (organization_id, resource.id, end, start),
        ).fetchall()
    return [
        (int(row['block_start_at']), int(row['block_end_at']))
        for row in rows
    ]

def _assert_resource_ownership(
    conn,
    organization_id: int,
    service_id: int,
    resource_id: int,
    calendar_id: int,
) -> None:
    row = conn.execute(
        '''
        SELECT 1
        FROM scheduling_service_resources sr
        JOIN scheduling_service_types s
          ON s.id=sr.service_id
         AND s.organization_id=sr.organization_id
        JOIN scheduling_resources r
          ON r.id=sr.resource_id
         AND r.organization_id=sr.organization_id
        WHERE sr.organization_id=?
          AND sr.service_id=?
          AND sr.resource_id=?
          AND s.calendar_id=?
          AND r.calendar_id=?
          AND s.status!='archived'
          AND r.status='active'
        LIMIT 1
        ''',
        (
            organization_id,
            service_id,
            resource_id,
            calendar_id,
            calendar_id,
        ),
    ).fetchone()
    if row is None:
        raise PermissionError(
            'Appointment resource ownership changed.'
        )


def _assert_no_conflict(
    conn,
    organization_id: int,
    resource_id: int,
    block_start: int,
    block_end: int,
) -> None:
    row = conn.execute(
        '''
        SELECT id
        FROM scheduling_appointments
        WHERE organization_id=?
          AND resource_id=?
          AND status IN ('pending','confirmed')
          AND block_start_at < ?
          AND block_end_at > ?
        LIMIT 1
        ''',
        (
            organization_id,
            resource_id,
            block_end,
            block_start,
        ),
    ).fetchone()
    if row is not None:
        raise ValueError(
            'Appointment conflicts with an existing resource booking.'
        )


def _actor_user(
    organization_slug: str,
    actor_user_id: int | None,
) -> int | None:
    if actor_user_id is None:
        return None
    access = scheduling_boundary.require(
        actor_user_id, organization_slug, 'manage'
    )
    return access.user_id


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


def _status(value: str) -> str:
    clean = (value or '').strip().lower()
    if clean not in APPOINTMENT_STATUSES:
        raise ValueError(
            f'Unknown appointment status: {clean}'
        )
    return clean


def _reason(value: str) -> str:
    clean = (value or '').strip()
    if len(clean) > 500:
        raise ValueError(
            'Appointment transition reason must be 500 characters or fewer.'
        )
    return clean


def _epoch(value: int, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f'{label} must be an integer UTC epoch.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f'{label} must be an integer UTC epoch.'
        ) from exc
    if clean < 0:
        raise ValueError(
            f'{label} must be an integer UTC epoch.'
        )
    return clean


def _positive_int(value: int, label: str) -> int:
    clean = _epoch(value, label)
    if clean <= 0:
        raise ValueError(f'{label} must be a positive integer.')
    return clean


def _appointment_row(
    conn,
    organization_id: int,
    appointment_id: int,
):
    return conn.execute(
        '''
        SELECT a.*,o.slug AS organization_slug
        FROM scheduling_appointments a
        JOIN auth_organizations o ON o.id=a.organization_id
        WHERE a.organization_id=? AND a.id=?
        LIMIT 1
        ''',
        (organization_id, appointment_id),
    ).fetchone()


def _appointment_from_row(row) -> Appointment:
    return Appointment(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        calendar_id=int(row['calendar_id']),
        service_id=int(row['service_id']),
        resource_id=int(row['resource_id']),
        customer_user_id=(
            int(row['customer_user_id'])
            if row['customer_user_id'] is not None
            else None
        ),
        crm_contact_id=(
            int(row['crm_contact_id'])
            if row['crm_contact_id'] is not None
            else None
        ),
        status=str(row['status']),
        start_at=int(row['start_at']),
        end_at=int(row['end_at']),
        block_start_at=int(row['block_start_at']),
        block_end_at=int(row['block_end_at']),
        duration_minutes=int(row['duration_minutes']),
        buffer_before_minutes=int(row['buffer_before_minutes']),
        buffer_after_minutes=int(row['buffer_after_minutes']),
        created_by_user_id=(
            int(row['created_by_user_id'])
            if row['created_by_user_id'] is not None
            else None
        ),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )


def _transition_from_row(row) -> AppointmentTransition:
    return AppointmentTransition(
        id=int(row['id']),
        appointment_id=int(row['appointment_id']),
        organization_id=int(row['organization_id']),
        from_status=str(row['from_status']),
        to_status=str(row['to_status']),
        actor_user_id=(
            int(row['actor_user_id'])
            if row['actor_user_id'] is not None
            else None
        ),
        reason=str(row['reason']),
        created_at=int(row['created_at']),
    )
)


class AppointmentConflictError(ValueError):
    pass
_TRANSITIONS = {
    'pending': {'confirmed', 'canceled'},
    'confirmed': {'canceled', 'completed', 'no_show'},
    'canceled': set(),
    'completed': set(),
    'no_show': set(),
}


@dataclass(frozen=True)
class Appointment:
    id: int
    organization_id: int
    organization_slug: str
    calendar_id: int
    service_id: int
    resource_id: int
    customer_user_id: int | None
    crm_contact_id: int | None
    status: str
    start_at: int
    end_at: int
    block_start_at: int
    block_end_at: int
    duration_minutes: int
    buffer_before_minutes: int
    buffer_after_minutes: int
    created_by_user_id: int | None
    created_at: int
    updated_at: int


@dataclass(frozen=True)
class AppointmentTransition:
    id: int
    appointment_id: int
    organization_id: int
    from_status: str
    to_status: str
    actor_user_id: int | None
    reason: str
    created_at: int


def ensure_schema() -> None:
    scheduling_availability.ensure_schema()
    crm_contacts.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS scheduling_appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                calendar_id INTEGER NOT NULL,
                service_id INTEGER NOT NULL,
                resource_id INTEGER NOT NULL,
                customer_user_id INTEGER,
                crm_contact_id INTEGER,
                status TEXT NOT NULL,
                start_at INTEGER NOT NULL,
                end_at INTEGER NOT NULL,
                block_start_at INTEGER NOT NULL,
                block_end_at INTEGER NOT NULL,
                duration_minutes INTEGER NOT NULL,
                buffer_before_minutes INTEGER NOT NULL,
                buffer_after_minutes INTEGER NOT NULL,
                created_by_user_id INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                CHECK(status IN (
                    'pending','confirmed','canceled','completed','no_show'
                )),
                CHECK(end_at > start_at),
                CHECK(block_end_at > block_start_at),
                CHECK(duration_minutes BETWEEN 5 AND 1440),
                CHECK(buffer_before_minutes BETWEEN 0 AND 1440),
                CHECK(buffer_after_minutes BETWEEN 0 AND 1440),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(calendar_id)
                    REFERENCES scheduling_calendars(id) ON DELETE RESTRICT,
                FOREIGN KEY(service_id)
                    REFERENCES scheduling_service_types(id) ON DELETE RESTRICT,
                FOREIGN KEY(resource_id)
                    REFERENCES scheduling_resources(id) ON DELETE RESTRICT,
                FOREIGN KEY(customer_user_id)
                    REFERENCES auth_users(id) ON DELETE SET NULL,
                FOREIGN KEY(crm_contact_id)
                    REFERENCES crm_v2_contacts(id) ON DELETE SET NULL,
                FOREIGN KEY(created_by_user_id)
                    REFERENCES auth_users(id) ON DELETE SET NULL
            )
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_scheduling_appointments_resource
            ON scheduling_appointments(
                organization_id,resource_id,start_at,end_at,status,id
            )
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_scheduling_appointments_customer
            ON scheduling_appointments(
                organization_id,customer_user_id,start_at,id
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS scheduling_appointment_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                appointment_id INTEGER NOT NULL,
                organization_id INTEGER NOT NULL,
                from_status TEXT NOT NULL,
                to_status TEXT NOT NULL,
                actor_user_id INTEGER,
                reason TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                FOREIGN KEY(appointment_id)
                    REFERENCES scheduling_appointments(id) ON DELETE CASCADE,
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(actor_user_id)
                    REFERENCES auth_users(id) ON DELETE SET NULL
            )
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_scheduling_appointment_transitions
            ON scheduling_appointment_transitions(
                organization_id,appointment_id,created_at,id
            )
            '''
        )
        conn.commit()


def create_appointment(
    organization_slug: str,
    *,
    service_id: int,
    resource_id: int,
    start_at: int,
    status: str = 'confirmed',
    customer_user_id: int | None = None,
    crm_contact_id: int | None = None,
    actor_user_id: int | None = None,
    reason: str = '',
) -> Appointment:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    service = scheduling_calendars.get_service_type(
        organization_slug, service_id
    )
    resource = scheduling_availability.get_resource(
        organization_slug, resource_id
    )
    if (
        service is None
        or service.status == 'archived'
        or resource is None
        or resource.status != 'active'
    ):
        raise PermissionError(
            'Appointment service/resource is unavailable.'
        )
    if service.calendar_id != resource.calendar_id:
        raise PermissionError(
            'Appointment service/resource must share a calendar.'
        )
    allowed_resources = scheduling_availability.list_service_resources(
        organization_slug, service.id
    )
    if resource.id not in {item.id for item in allowed_resources}:
        raise PermissionError(
            'Resource is not assigned to this service.'
        )

    clean_status = _status(status)
    if clean_status not in {'pending', 'confirmed'}:
        raise ValueError(
            'New appointments must start pending or confirmed.'
        )

    clean_customer = scheduling_boundary.require_customer_user(
        organization_slug, customer_user_id
    )
    clean_contact = scheduling_boundary.require_contact(
        organization_slug, crm_contact_id
    )
    clean_actor = _actor_user(
        organization_slug, actor_user_id
    )

    start = _epoch(start_at, 'start_at')
    duration = int(service.duration_minutes)
    before = int(service.buffer_before_minutes)
    after = int(service.buffer_after_minutes)
    end = start + (duration * 60)
    block_start = start - (before * 60)
    block_end = end + (after * 60)
    if block_start < 0:
        raise ValueError(
            'Appointment buffer would precede the UTC epoch.'
        )

    now = tenant_auth.now()
    clean_reason = _reason(reason)
    with tenant_auth.db() as conn:
        conn.commit()
        conn.execute('BEGIN IMMEDIATE')
        _assert_resource_ownership(
            conn,
            organization_id,
            service.id,
            resource.id,
            service.calendar_id,
        )
        _assert_no_conflict(
            conn,
            organization_id,
            resource.id,
            block_start,
            block_end,
        )
        cur = conn.execute(
            '''
            INSERT INTO scheduling_appointments(
                organization_id,calendar_id,service_id,resource_id,
                customer_user_id,crm_contact_id,status,start_at,end_at,
                block_start_at,block_end_at,duration_minutes,
                buffer_before_minutes,buffer_after_minutes,
                created_by_user_id,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''',
            (
                organization_id,
                service.calendar_id,
                service.id,
                resource.id,
                clean_customer,
                clean_contact,
                clean_status,
                start,
                end,
                block_start,
                block_end,
                duration,
                before,
                after,
                clean_actor,
                now,
                now,
            ),
        )
        appointment_id = int(cur.lastrowid)
        conn.execute(
            '''
            INSERT INTO scheduling_appointment_transitions(
                appointment_id,organization_id,from_status,to_status,
                actor_user_id,reason,created_at
            ) VALUES(?,?,'new',?,?,?,?)
            ''',
            (
                appointment_id,
                organization_id,
                clean_status,
                clean_actor,
                clean_reason,
                now,
            ),
        )
        conn.commit()
        row = _appointment_row(
            conn, organization_id, appointment_id
        )
    return _appointment_from_row(row)


def get_appointment(
    organization_slug: str,
    appointment_id: int,
) -> Appointment | None:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    with tenant_auth.db() as conn:
        row = _appointment_row(
            conn,
            organization_id,
            _positive_int(appointment_id, 'appointment_id'),
        )
    return _appointment_from_row(row) if row else None


def list_appointments(
    organization_slug: str,
    *,
    resource_id: int | None = None,
    customer_user_id: int | None = None,
    start_at: int | None = None,
    end_at: int | None = None,
    include_canceled: bool = False,
) -> list[Appointment]:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    sql = '''
        SELECT a.*,o.slug AS organization_slug
        FROM scheduling_appointments a
        JOIN auth_organizations o ON o.id=a.organization_id
        WHERE a.organization_id=?
    '''
    params: list[object] = [organization_id]
    if resource_id is not None:
        resource = scheduling_availability.get_resource(
            organization_slug, resource_id
        )
        if resource is None:
            return []
        sql += ' AND a.resource_id=?'
        params.append(resource.id)
    if customer_user_id is not None:
        customer_id = scheduling_boundary.require_customer_user(
            organization_slug, customer_user_id
        )
        sql += ' AND a.customer_user_id=?'
        params.append(customer_id)
    if start_at is not None and end_at is not None:
        start, end = scheduling_boundary.validate_utc_range(
            start_at, end_at
        )
        sql += ' AND a.start_at < ? AND a.end_at > ?'
        params.extend([end, start])
    elif start_at is not None or end_at is not None:
        raise ValueError(
            'Appointment time filtering requires start_at and end_at.'
        )
    if not include_canceled:
        sql += " AND a.status!='canceled'"
    sql += ' ORDER BY a.start_at,a.id'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_appointment_from_row(row) for row in rows]


def transition_appointment(
    organization_slug: str,
    appointment_id: int,
    *,
    to_status: str,
    actor_user_id: int | None = None,
    reason: str = '',
) -> Appointment:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    appointment_id = _positive_int(
        appointment_id, 'appointment_id'
    )
    clean_status = _status(to_status)
    clean_actor = _actor_user(
        organization_slug, actor_user_id
    )
    clean_reason = _reason(reason)
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        conn.commit()
        conn.execute('BEGIN IMMEDIATE')
        row = _appointment_row(
            conn, organization_id, appointment_id
        )
        if row is None:
            conn.rollback()
            raise ValueError('Appointment not found.')
        current = str(row['status'])
        if clean_status == current:
            conn.rollback()
            return _appointment_from_row(row)
        if clean_status not in _TRANSITIONS.get(current, set()):
            conn.rollback()
            raise ValueError(
                f'Invalid appointment transition: '
                f'{current} -> {clean_status}.'
            )
        conn.execute(
            '''
            UPDATE scheduling_appointments
            SET status=?,updated_at=?
            WHERE organization_id=? AND id=?
            ''',
            (
                clean_status,
                now,
                organization_id,
                appointment_id,
            ),
        )
        conn.execute(
            '''
            INSERT INTO scheduling_appointment_transitions(
                appointment_id,organization_id,from_status,to_status,
                actor_user_id,reason,created_at
            ) VALUES(?,?,?,?,?,?,?)
            ''',
            (
                appointment_id,
                organization_id,
                current,
                clean_status,
                clean_actor,
                clean_reason,
                now,
            ),
        )
        conn.commit()
        updated = _appointment_row(
            conn, organization_id, appointment_id
        )
    return _appointment_from_row(updated)


def list_transitions(
    organization_slug: str,
    appointment_id: int,
) -> list[AppointmentTransition]:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    appointment = get_appointment(
        organization_slug, appointment_id
    )
    if appointment is None:
        return []
    with tenant_auth.db() as conn:
        rows = conn.execute(
            '''
            SELECT *
            FROM scheduling_appointment_transitions
            WHERE organization_id=? AND appointment_id=?
            ORDER BY created_at,id
            ''',
            (organization_id, appointment.id),
        ).fetchall()
    return [_transition_from_row(row) for row in rows]



def list_blocking_intervals(
    organization_slug: str,
    resource_id: int,
    *,
    start_at: int,
    end_at: int,
) -> list[tuple[int, int]]:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    resource = scheduling_availability.get_resource(
        organization_slug, resource_id
    )
    if resource is None or resource.status != 'active':
        return []
    start, end = scheduling_boundary.validate_utc_range(
        start_at, end_at
    )
    with tenant_auth.db() as conn:
        rows = conn.execute(
            """
            SELECT block_start_at,block_end_at
            FROM scheduling_appointments
            WHERE organization_id=?
              AND resource_id=?
              AND status IN ('pending','confirmed')
              AND block_start_at < ?
              AND block_end_at > ?
            ORDER BY block_start_at,block_end_at,id
            """,
            (organization_id, resource.id, end, start),
        ).fetchall()
    return [
        (int(row['block_start_at']), int(row['block_end_at']))
        for row in rows
    ]

def _assert_resource_ownership(
    conn,
    organization_id: int,
    service_id: int,
    resource_id: int,
    calendar_id: int,
) -> None:
    row = conn.execute(
        '''
        SELECT 1
        FROM scheduling_service_resources sr
        JOIN scheduling_service_types s
          ON s.id=sr.service_id
         AND s.organization_id=sr.organization_id
        JOIN scheduling_resources r
          ON r.id=sr.resource_id
         AND r.organization_id=sr.organization_id
        WHERE sr.organization_id=?
          AND sr.service_id=?
          AND sr.resource_id=?
          AND s.calendar_id=?
          AND r.calendar_id=?
          AND s.status!='archived'
          AND r.status='active'
        LIMIT 1
        ''',
        (
            organization_id,
            service_id,
            resource_id,
            calendar_id,
            calendar_id,
        ),
    ).fetchone()
    if row is None:
        raise PermissionError(
            'Appointment resource ownership changed.'
        )


def _assert_no_conflict(
    conn,
    organization_id: int,
    resource_id: int,
    block_start: int,
    block_end: int,
) -> None:
    row = conn.execute(
        '''
        SELECT id
        FROM scheduling_appointments
        WHERE organization_id=?
          AND resource_id=?
          AND status IN ('pending','confirmed')
          AND block_start_at < ?
          AND block_end_at > ?
        LIMIT 1
        ''',
        (
            organization_id,
            resource_id,
            block_end,
            block_start,
        ),
    ).fetchone()
    if row is not None:
        raise ValueError(
            'Appointment conflicts with an existing resource booking.'
        )


def _actor_user(
    organization_slug: str,
    actor_user_id: int | None,
) -> int | None:
    if actor_user_id is None:
        return None
    access = scheduling_boundary.require(
        actor_user_id, organization_slug, 'manage'
    )
    return access.user_id


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


def _status(value: str) -> str:
    clean = (value or '').strip().lower()
    if clean not in APPOINTMENT_STATUSES:
        raise ValueError(
            f'Unknown appointment status: {clean}'
        )
    return clean


def _reason(value: str) -> str:
    clean = (value or '').strip()
    if len(clean) > 500:
        raise ValueError(
            'Appointment transition reason must be 500 characters or fewer.'
        )
    return clean


def _epoch(value: int, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f'{label} must be an integer UTC epoch.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f'{label} must be an integer UTC epoch.'
        ) from exc
    if clean < 0:
        raise ValueError(
            f'{label} must be an integer UTC epoch.'
        )
    return clean


def _positive_int(value: int, label: str) -> int:
    clean = _epoch(value, label)
    if clean <= 0:
        raise ValueError(f'{label} must be a positive integer.')
    return clean


def _appointment_row(
    conn,
    organization_id: int,
    appointment_id: int,
):
    return conn.execute(
        '''
        SELECT a.*,o.slug AS organization_slug
        FROM scheduling_appointments a
        JOIN auth_organizations o ON o.id=a.organization_id
        WHERE a.organization_id=? AND a.id=?
        LIMIT 1
        ''',
        (organization_id, appointment_id),
    ).fetchone()


def _appointment_from_row(row) -> Appointment:
    return Appointment(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        calendar_id=int(row['calendar_id']),
        service_id=int(row['service_id']),
        resource_id=int(row['resource_id']),
        customer_user_id=(
            int(row['customer_user_id'])
            if row['customer_user_id'] is not None
            else None
        ),
        crm_contact_id=(
            int(row['crm_contact_id'])
            if row['crm_contact_id'] is not None
            else None
        ),
        status=str(row['status']),
        start_at=int(row['start_at']),
        end_at=int(row['end_at']),
        block_start_at=int(row['block_start_at']),
        block_end_at=int(row['block_end_at']),
        duration_minutes=int(row['duration_minutes']),
        buffer_before_minutes=int(row['buffer_before_minutes']),
        buffer_after_minutes=int(row['buffer_after_minutes']),
        created_by_user_id=(
            int(row['created_by_user_id'])
            if row['created_by_user_id'] is not None
            else None
        ),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )


def _transition_from_row(row) -> AppointmentTransition:
    return AppointmentTransition(
        id=int(row['id']),
        appointment_id=int(row['appointment_id']),
        organization_id=int(row['organization_id']),
        from_status=str(row['from_status']),
        to_status=str(row['to_status']),
        actor_user_id=(
            int(row['actor_user_id'])
            if row['actor_user_id'] is not None
            else None
        ),
        reason=str(row['reason']),
        created_at=int(row['created_at']),
    )
