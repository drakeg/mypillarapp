from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3

import scheduling_boundary
import tenant_auth
import tenant_sites


CALENDAR_STATUSES = {'draft', 'published', 'archived'}
SERVICE_STATUSES = {'draft', 'published', 'archived'}
_SLUG_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


@dataclass(frozen=True)
class SchedulingCalendar:
    id: int
    organization_id: int
    organization_slug: str
    site_id: int | None
    slug: str
    name: str
    timezone: str
    status: str
    booking_horizon_days: int
    minimum_notice_minutes: int
    created_at: int
    updated_at: int


@dataclass(frozen=True)
class ServiceType:
    id: int
    organization_id: int
    organization_slug: str
    calendar_id: int
    calendar_slug: str
    slug: str
    name: str
    description: str
    duration_minutes: int
    buffer_before_minutes: int
    buffer_after_minutes: int
    status: str
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    tenant_sites.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS scheduling_calendars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                site_id INTEGER,
                slug TEXT NOT NULL,
                name TEXT NOT NULL,
                timezone TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                booking_horizon_days INTEGER NOT NULL DEFAULT 90,
                minimum_notice_minutes INTEGER NOT NULL DEFAULT 60,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(organization_id, slug),
                CHECK(status IN ('draft','published','archived')),
                CHECK(booking_horizon_days BETWEEN 1 AND 730),
                CHECK(minimum_notice_minutes BETWEEN 0 AND 43200),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(site_id)
                    REFERENCES site_builder_sites(id) ON DELETE SET NULL
            )
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_scheduling_calendars_org_status
            ON scheduling_calendars(organization_id,status,name COLLATE NOCASE,id)
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS scheduling_service_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                calendar_id INTEGER NOT NULL,
                slug TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                duration_minutes INTEGER NOT NULL,
                buffer_before_minutes INTEGER NOT NULL DEFAULT 0,
                buffer_after_minutes INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(calendar_id, slug),
                CHECK(duration_minutes BETWEEN 5 AND 1440),
                CHECK(buffer_before_minutes BETWEEN 0 AND 1440),
                CHECK(buffer_after_minutes BETWEEN 0 AND 1440),
                CHECK(status IN ('draft','published','archived')),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(calendar_id)
                    REFERENCES scheduling_calendars(id) ON DELETE CASCADE
            )
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_scheduling_services_calendar_status
            ON scheduling_service_types(
                organization_id,calendar_id,status,name COLLATE NOCASE,id
            )
            '''
        )
        conn.commit()


def create_calendar(
    organization_slug: str,
    *,
    slug: str,
    name: str,
    timezone_name: str,
    site_id: int | None = None,
    status: str = 'draft',
    booking_horizon_days: int = 90,
    minimum_notice_minutes: int = 60,
) -> SchedulingCalendar:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    clean_slug = _slug(slug, 'Calendar')
    clean_name = _name(name, 'Calendar')
    clean_timezone = scheduling_boundary.normalize_timezone(timezone_name)
    clean_status = _status(status, CALENDAR_STATUSES, 'calendar')
    clean_horizon = _bounded_int(
        booking_horizon_days, 1, 730, 'Booking horizon days'
    )
    clean_notice = _bounded_int(
        minimum_notice_minutes, 0, 43200, 'Minimum notice minutes'
    )
    clean_site_id = scheduling_boundary.require_site(
        organization_slug, site_id
    )
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        try:
            cur = conn.execute(
                '''
                INSERT INTO scheduling_calendars(
                    organization_id,site_id,slug,name,timezone,status,
                    booking_horizon_days,minimum_notice_minutes,
                    created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                ''',
                (
                    organization_id,
                    clean_site_id,
                    clean_slug,
                    clean_name,
                    clean_timezone,
                    clean_status,
                    clean_horizon,
                    clean_notice,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                'A calendar with that slug already exists for this organization.'
            ) from exc
        conn.commit()
        row = _calendar_row(conn, organization_id, int(cur.lastrowid))
    return _calendar_from_row(row)


def get_calendar(
    organization_slug: str,
    calendar_id: int,
) -> SchedulingCalendar | None:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    with tenant_auth.db() as conn:
        row = _calendar_row(
            conn,
            organization_id,
            _positive_int(calendar_id, 'calendar_id'),
        )
    return _calendar_from_row(row) if row else None


def list_calendars(
    organization_slug: str,
    *,
    published_only: bool = False,
    include_archived: bool = False,
) -> list[SchedulingCalendar]:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    sql = '''
        SELECT c.*,o.slug AS organization_slug
        FROM scheduling_calendars c
        JOIN auth_organizations o ON o.id=c.organization_id
        WHERE c.organization_id=?
    '''
    params: list[object] = [organization_id]
    if published_only:
        sql += " AND c.status='published'"
    elif not include_archived:
        sql += " AND c.status!='archived'"
    sql += ' ORDER BY c.name COLLATE NOCASE,c.id'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_calendar_from_row(row) for row in rows]


def update_calendar(
    organization_slug: str,
    calendar_id: int,
    *,
    name: str | None = None,
    timezone_name: str | None = None,
    site_id: int | None | object = ...,
    status: str | None = None,
    booking_horizon_days: int | None = None,
    minimum_notice_minutes: int | None = None,
) -> SchedulingCalendar | None:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    calendar_id = _positive_int(calendar_id, 'calendar_id')
    with tenant_auth.db() as conn:
        existing = _calendar_row(conn, organization_id, calendar_id)
        if existing is None:
            return None
        if str(existing['status']) == 'archived':
            raise ValueError('Archived calendars cannot be updated.')

        assignments: list[str] = []
        params: list[object] = []
        if name is not None:
            assignments.append('name=?')
            params.append(_name(name, 'Calendar'))
        if timezone_name is not None:
            assignments.append('timezone=?')
            params.append(
                scheduling_boundary.normalize_timezone(timezone_name)
            )
        if site_id is not ...:
            assignments.append('site_id=?')
            params.append(
                scheduling_boundary.require_site(
                    organization_slug, site_id
                )
            )
        if status is not None:
            assignments.append('status=?')
            params.append(
                _status(status, CALENDAR_STATUSES, 'calendar')
            )
        if booking_horizon_days is not None:
            assignments.append('booking_horizon_days=?')
            params.append(
                _bounded_int(
                    booking_horizon_days,
                    1,
                    730,
                    'Booking horizon days',
                )
            )
        if minimum_notice_minutes is not None:
            assignments.append('minimum_notice_minutes=?')
            params.append(
                _bounded_int(
                    minimum_notice_minutes,
                    0,
                    43200,
                    'Minimum notice minutes',
                )
            )
        if not assignments:
            return _calendar_from_row(existing)
        assignments.append('updated_at=?')
        params.append(tenant_auth.now())
        params.extend([organization_id, calendar_id])
        conn.execute(
            f'''
            UPDATE scheduling_calendars
            SET {', '.join(assignments)}
            WHERE organization_id=? AND id=?
            ''',
            params,
        )
        conn.commit()
        row = _calendar_row(conn, organization_id, calendar_id)
    return _calendar_from_row(row)


def archive_calendar(
    organization_slug: str,
    calendar_id: int,
) -> SchedulingCalendar | None:
    current = get_calendar(organization_slug, calendar_id)
    if current is None:
        return None
    if current.status == 'archived':
        return current
    return update_calendar(
        organization_slug, calendar_id, status='archived'
    )


def create_service_type(
    organization_slug: str,
    calendar_id: int,
    *,
    slug: str,
    name: str,
    duration_minutes: int,
    description: str = '',
    buffer_before_minutes: int = 0,
    buffer_after_minutes: int = 0,
    status: str = 'draft',
) -> ServiceType:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    calendar = get_calendar(organization_slug, calendar_id)
    if calendar is None or calendar.status == 'archived':
        raise PermissionError(
            'Bookable service calendar is unavailable for this tenant.'
        )
    clean_slug = _slug(slug, 'Service')
    clean_name = _name(name, 'Service')
    clean_duration = _bounded_int(
        duration_minutes, 5, 1440, 'Service duration minutes'
    )
    before = _bounded_int(
        buffer_before_minutes, 0, 1440, 'Buffer before minutes'
    )
    after = _bounded_int(
        buffer_after_minutes, 0, 1440, 'Buffer after minutes'
    )
    clean_status = _status(status, SERVICE_STATUSES, 'service')
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        try:
            cur = conn.execute(
                '''
                INSERT INTO scheduling_service_types(
                    organization_id,calendar_id,slug,name,description,
                    duration_minutes,buffer_before_minutes,
                    buffer_after_minutes,status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ''',
                (
                    organization_id,
                    calendar.id,
                    clean_slug,
                    clean_name,
                    _description(description),
                    clean_duration,
                    before,
                    after,
                    clean_status,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                'A service with that slug already exists for this calendar.'
            ) from exc
        conn.commit()
        row = _service_row(conn, organization_id, int(cur.lastrowid))
    return _service_from_row(row)


def get_service_type(
    organization_slug: str,
    service_id: int,
) -> ServiceType | None:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    with tenant_auth.db() as conn:
        row = _service_row(
            conn,
            organization_id,
            _positive_int(service_id, 'service_id'),
        )
    return _service_from_row(row) if row else None


def list_service_types(
    organization_slug: str,
    calendar_id: int,
    *,
    published_only: bool = False,
    include_archived: bool = False,
) -> list[ServiceType]:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    calendar = get_calendar(organization_slug, calendar_id)
    if calendar is None:
        return []
    sql = '''
        SELECT s.*,o.slug AS organization_slug,c.slug AS calendar_slug
        FROM scheduling_service_types s
        JOIN auth_organizations o ON o.id=s.organization_id
        JOIN scheduling_calendars c
          ON c.id=s.calendar_id AND c.organization_id=s.organization_id
        WHERE s.organization_id=? AND s.calendar_id=?
    '''
    params: list[object] = [organization_id, calendar.id]
    if published_only:
        sql += " AND s.status='published'"
    elif not include_archived:
        sql += " AND s.status!='archived'"
    sql += ' ORDER BY s.name COLLATE NOCASE,s.id'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_service_from_row(row) for row in rows]


def update_service_type(
    organization_slug: str,
    service_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    duration_minutes: int | None = None,
    buffer_before_minutes: int | None = None,
    buffer_after_minutes: int | None = None,
    status: str | None = None,
) -> ServiceType | None:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    service_id = _positive_int(service_id, 'service_id')
    with tenant_auth.db() as conn:
        existing = _service_row(conn, organization_id, service_id)
        if existing is None:
            return None
        if str(existing['status']) == 'archived':
            raise ValueError('Archived services cannot be updated.')
        calendar = _calendar_row(
            conn,
            organization_id,
            int(existing['calendar_id']),
        )
        if calendar is None or str(calendar['status']) == 'archived':
            raise PermissionError('Service calendar is unavailable.')

        assignments: list[str] = []
        params: list[object] = []
        if name is not None:
            assignments.append('name=?')
            params.append(_name(name, 'Service'))
        if description is not None:
            assignments.append('description=?')
            params.append(_description(description))
        if duration_minutes is not None:
            assignments.append('duration_minutes=?')
            params.append(
                _bounded_int(
                    duration_minutes, 5, 1440,
                    'Service duration minutes'
                )
            )
        if buffer_before_minutes is not None:
            assignments.append('buffer_before_minutes=?')
            params.append(
                _bounded_int(
                    buffer_before_minutes, 0, 1440,
                    'Buffer before minutes'
                )
            )
        if buffer_after_minutes is not None:
            assignments.append('buffer_after_minutes=?')
            params.append(
                _bounded_int(
                    buffer_after_minutes, 0, 1440,
                    'Buffer after minutes'
                )
            )
        if status is not None:
            assignments.append('status=?')
            params.append(
                _status(status, SERVICE_STATUSES, 'service')
            )
        if not assignments:
            return _service_from_row(existing)
        assignments.append('updated_at=?')
        params.append(tenant_auth.now())
        params.extend([organization_id, service_id])
        conn.execute(
            f'''
            UPDATE scheduling_service_types
            SET {', '.join(assignments)}
            WHERE organization_id=? AND id=?
            ''',
            params,
        )
        conn.commit()
        row = _service_row(conn, organization_id, service_id)
    return _service_from_row(row)


def archive_service_type(
    organization_slug: str,
    service_id: int,
) -> ServiceType | None:
    current = get_service_type(organization_slug, service_id)
    if current is None:
        return None
    if current.status == 'archived':
        return current
    return update_service_type(
        organization_slug, service_id, status='archived'
    )


def _organization_id(organization_slug: str) -> int:
    access_row = (organization_slug or '').strip().lower()
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''SELECT id FROM auth_organizations
               WHERE slug=? AND status='active' LIMIT 1''',
            (access_row,),
        ).fetchone()
    if row is None:
        raise PermissionError('Scheduling organization is not active.')
    return int(row['id'])


def _calendar_row(conn, organization_id: int, calendar_id: int):
    return conn.execute(
        '''
        SELECT c.*,o.slug AS organization_slug
        FROM scheduling_calendars c
        JOIN auth_organizations o ON o.id=c.organization_id
        WHERE c.organization_id=? AND c.id=?
        LIMIT 1
        ''',
        (organization_id, calendar_id),
    ).fetchone()


def _service_row(conn, organization_id: int, service_id: int):
    return conn.execute(
        '''
        SELECT s.*,o.slug AS organization_slug,c.slug AS calendar_slug
        FROM scheduling_service_types s
        JOIN auth_organizations o ON o.id=s.organization_id
        JOIN scheduling_calendars c
          ON c.id=s.calendar_id AND c.organization_id=s.organization_id
        WHERE s.organization_id=? AND s.id=?
        LIMIT 1
        ''',
        (organization_id, service_id),
    ).fetchone()


def _slug(value: str, label: str) -> str:
    clean = (value or '').strip().lower()
    if not clean or not _SLUG_RE.fullmatch(clean):
        raise ValueError(
            f'{label} slug must contain lowercase letters/numbers '
            'separated by hyphens.'
        )
    if len(clean) > 100:
        raise ValueError(f'{label} slug must be 100 characters or fewer.')
    return clean


def _name(value: str, label: str) -> str:
    clean = (value or '').strip()
    if not clean:
        raise ValueError(f'{label} name is required.')
    if len(clean) > 200:
        raise ValueError(f'{label} name must be 200 characters or fewer.')
    return clean


def _description(value: str) -> str:
    clean = value or ''
    if len(clean) > 4000:
        raise ValueError('Service description must be 4000 characters or fewer.')
    return clean


def _status(value: str, allowed: set[str], label: str) -> str:
    clean = (value or '').strip().lower()
    if clean not in allowed:
        raise ValueError(f'Unknown {label} status: {clean}')
    return clean


def _bounded_int(
    value: int,
    minimum: int,
    maximum: int,
    label: str,
) -> int:
    if isinstance(value, bool):
        raise ValueError(
            f'{label} must be between {minimum} and {maximum}.'
        )
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f'{label} must be between {minimum} and {maximum}.'
        ) from exc
    if clean < minimum or clean > maximum:
        raise ValueError(
            f'{label} must be between {minimum} and {maximum}.'
        )
    return clean


def _positive_int(value: int, label: str) -> int:
    return _bounded_int(value, 1, 2_147_483_647, label)


def _calendar_from_row(row) -> SchedulingCalendar:
    return SchedulingCalendar(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        site_id=(
            int(row['site_id']) if row['site_id'] is not None else None
        ),
        slug=str(row['slug']),
        name=str(row['name']),
        timezone=str(row['timezone']),
        status=str(row['status']),
        booking_horizon_days=int(row['booking_horizon_days']),
        minimum_notice_minutes=int(row['minimum_notice_minutes']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )


def _service_from_row(row) -> ServiceType:
    return ServiceType(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        calendar_id=int(row['calendar_id']),
        calendar_slug=str(row['calendar_slug']),
        slug=str(row['slug']),
        name=str(row['name']),
        description=str(row['description']),
        duration_minutes=int(row['duration_minutes']),
        buffer_before_minutes=int(row['buffer_before_minutes']),
        buffer_after_minutes=int(row['buffer_after_minutes']),
        status=str(row['status']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
