from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3

import scheduling_boundary
import scheduling_calendars
import tenant_auth
import tenant_memberships


RESOURCE_KINDS = {'staff', 'room', 'equipment', 'other'}
RESOURCE_STATUSES = {'active', 'archived'}
_SLUG_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


@dataclass(frozen=True)
class SchedulingResource:
    id: int
    organization_id: int
    organization_slug: str
    calendar_id: int
    calendar_slug: str
    user_id: int | None
    slug: str
    name: str
    kind: str
    status: str
    created_at: int
    updated_at: int


@dataclass(frozen=True)
class WeeklyAvailability:
    id: int
    organization_id: int
    resource_id: int
    weekday: int
    start_minute: int
    end_minute: int
    created_at: int


@dataclass(frozen=True)
class BlackoutPeriod:
    id: int
    organization_id: int
    resource_id: int
    start_at: int
    end_at: int
    reason: str
    created_at: int


def ensure_schema() -> None:
    scheduling_calendars.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS scheduling_resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                calendar_id INTEGER NOT NULL,
                user_id INTEGER,
                slug TEXT NOT NULL,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(calendar_id, slug),
                CHECK(kind IN ('staff','room','equipment','other')),
                CHECK(status IN ('active','archived')),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(calendar_id)
                    REFERENCES scheduling_calendars(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id)
                    REFERENCES auth_users(id) ON DELETE SET NULL
            )
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_scheduling_resources_calendar
            ON scheduling_resources(
                organization_id,calendar_id,status,name COLLATE NOCASE,id
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS scheduling_weekly_availability (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                resource_id INTEGER NOT NULL,
                weekday INTEGER NOT NULL,
                start_minute INTEGER NOT NULL,
                end_minute INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                UNIQUE(resource_id,weekday,start_minute,end_minute),
                CHECK(weekday BETWEEN 0 AND 6),
                CHECK(start_minute BETWEEN 0 AND 1439),
                CHECK(end_minute BETWEEN 1 AND 1440),
                CHECK(end_minute > start_minute),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(resource_id)
                    REFERENCES scheduling_resources(id) ON DELETE CASCADE
            )
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_scheduling_availability_resource
            ON scheduling_weekly_availability(
                organization_id,resource_id,weekday,start_minute
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS scheduling_blackouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                resource_id INTEGER NOT NULL,
                start_at INTEGER NOT NULL,
                end_at INTEGER NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                CHECK(end_at > start_at),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(resource_id)
                    REFERENCES scheduling_resources(id) ON DELETE CASCADE
            )
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_scheduling_blackouts_resource
            ON scheduling_blackouts(
                organization_id,resource_id,start_at,end_at,id
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS scheduling_service_resources (
                organization_id INTEGER NOT NULL,
                service_id INTEGER NOT NULL,
                resource_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY(service_id,resource_id),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(service_id)
                    REFERENCES scheduling_service_types(id) ON DELETE CASCADE,
                FOREIGN KEY(resource_id)
                    REFERENCES scheduling_resources(id) ON DELETE CASCADE
            )
            '''
        )
        conn.commit()


def create_resource(
    organization_slug: str,
    calendar_id: int,
    *,
    slug: str,
    name: str,
    kind: str = 'staff',
    user_id: int | None = None,
) -> SchedulingResource:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    calendar = scheduling_calendars.get_calendar(
        organization_slug, calendar_id
    )
    if calendar is None or calendar.status == 'archived':
        raise PermissionError('Scheduling calendar is unavailable.')
    clean_kind = _kind(kind)
    clean_user_id = _staff_user_id(
        organization_slug, user_id, clean_kind
    )
    clean_slug = _slug(slug)
    clean_name = _name(name)
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        try:
            cur = conn.execute(
                '''
                INSERT INTO scheduling_resources(
                    organization_id,calendar_id,user_id,slug,name,kind,
                    status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,'active',?,?)
                ''',
                (
                    organization_id,
                    calendar.id,
                    clean_user_id,
                    clean_slug,
                    clean_name,
                    clean_kind,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                'A resource with that slug already exists for this calendar.'
            ) from exc
        conn.commit()
        row = _resource_row(conn, organization_id, int(cur.lastrowid))
    return _resource_from_row(row)


def get_resource(
    organization_slug: str,
    resource_id: int,
) -> SchedulingResource | None:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    with tenant_auth.db() as conn:
        row = _resource_row(
            conn, organization_id, _positive_int(resource_id, 'resource_id')
        )
    return _resource_from_row(row) if row else None


def list_resources(
    organization_slug: str,
    calendar_id: int,
    *,
    include_archived: bool = False,
) -> list[SchedulingResource]:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    calendar = scheduling_calendars.get_calendar(
        organization_slug, calendar_id
    )
    if calendar is None:
        return []
    sql = '''
        SELECT r.*,o.slug AS organization_slug,c.slug AS calendar_slug
        FROM scheduling_resources r
        JOIN auth_organizations o ON o.id=r.organization_id
        JOIN scheduling_calendars c
          ON c.id=r.calendar_id AND c.organization_id=r.organization_id
        WHERE r.organization_id=? AND r.calendar_id=?
    '''
    params: list[object] = [organization_id, calendar.id]
    if not include_archived:
        sql += " AND r.status!='archived'"
    sql += ' ORDER BY r.name COLLATE NOCASE,r.id'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_resource_from_row(row) for row in rows]


def archive_resource(
    organization_slug: str,
    resource_id: int,
) -> SchedulingResource | None:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    resource_id = _positive_int(resource_id, 'resource_id')
    with tenant_auth.db() as conn:
        row = _resource_row(conn, organization_id, resource_id)
        if row is None:
            return None
        if str(row['status']) != 'archived':
            conn.execute(
                '''
                UPDATE scheduling_resources
                SET status='archived',updated_at=?
                WHERE organization_id=? AND id=?
                ''',
                (tenant_auth.now(), organization_id, resource_id),
            )
            conn.commit()
        row = _resource_row(conn, organization_id, resource_id)
    return _resource_from_row(row)


def add_weekly_availability(
    organization_slug: str,
    resource_id: int,
    *,
    weekday: int,
    start_minute: int,
    end_minute: int,
) -> WeeklyAvailability:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    resource = _active_resource(
        organization_slug, resource_id
    )
    clean_weekday = _bounded_int(weekday, 0, 6, 'weekday')
    clean_start = _bounded_int(
        start_minute, 0, 1439, 'start_minute'
    )
    clean_end = _bounded_int(end_minute, 1, 1440, 'end_minute')
    if clean_end <= clean_start:
        raise ValueError('Availability end must be after start.')
    with tenant_auth.db() as conn:
        overlap = conn.execute(
            '''
            SELECT 1
            FROM scheduling_weekly_availability
            WHERE organization_id=? AND resource_id=? AND weekday=?
              AND start_minute < ? AND end_minute > ?
            LIMIT 1
            ''',
            (
                organization_id,
                resource.id,
                clean_weekday,
                clean_end,
                clean_start,
            ),
        ).fetchone()
        if overlap is not None:
            raise ValueError(
                'Weekly availability cannot overlap an existing window.'
            )
        cur = conn.execute(
            '''
            INSERT INTO scheduling_weekly_availability(
                organization_id,resource_id,weekday,start_minute,
                end_minute,created_at
            ) VALUES(?,?,?,?,?,?)
            ''',
            (
                organization_id,
                resource.id,
                clean_weekday,
                clean_start,
                clean_end,
                tenant_auth.now(),
            ),
        )
        conn.commit()
        row = conn.execute(
            '''
            SELECT *
            FROM scheduling_weekly_availability
            WHERE id=? AND organization_id=?
            ''',
            (int(cur.lastrowid), organization_id),
        ).fetchone()
    return _availability_from_row(row)


def list_weekly_availability(
    organization_slug: str,
    resource_id: int,
) -> list[WeeklyAvailability]:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    resource = get_resource(organization_slug, resource_id)
    if resource is None:
        return []
    with tenant_auth.db() as conn:
        rows = conn.execute(
            '''
            SELECT *
            FROM scheduling_weekly_availability
            WHERE organization_id=? AND resource_id=?
            ORDER BY weekday,start_minute,end_minute,id
            ''',
            (organization_id, resource.id),
        ).fetchall()
    return [_availability_from_row(row) for row in rows]


def add_blackout(
    organization_slug: str,
    resource_id: int,
    *,
    start_at: int,
    end_at: int,
    reason: str = '',
) -> BlackoutPeriod:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    resource = _active_resource(organization_slug, resource_id)
    start, end = scheduling_boundary.validate_utc_range(
        start_at, end_at
    )
    clean_reason = (reason or '').strip()
    if len(clean_reason) > 500:
        raise ValueError('Blackout reason must be 500 characters or fewer.')
    with tenant_auth.db() as conn:
        cur = conn.execute(
            '''
            INSERT INTO scheduling_blackouts(
                organization_id,resource_id,start_at,end_at,reason,created_at
            ) VALUES(?,?,?,?,?,?)
            ''',
            (
                organization_id,
                resource.id,
                start,
                end,
                clean_reason,
                tenant_auth.now(),
            ),
        )
        conn.commit()
        row = conn.execute(
            '''
            SELECT *
            FROM scheduling_blackouts
            WHERE id=? AND organization_id=?
            ''',
            (int(cur.lastrowid), organization_id),
        ).fetchone()
    return _blackout_from_row(row)


def list_blackouts(
    organization_slug: str,
    resource_id: int,
    *,
    start_at: int | None = None,
    end_at: int | None = None,
) -> list[BlackoutPeriod]:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    resource = get_resource(organization_slug, resource_id)
    if resource is None:
        return []
    sql = '''
        SELECT *
        FROM scheduling_blackouts
        WHERE organization_id=? AND resource_id=?
    '''
    params: list[object] = [organization_id, resource.id]
    if start_at is not None and end_at is not None:
        start, end = scheduling_boundary.validate_utc_range(
            start_at, end_at
        )
        sql += ' AND start_at < ? AND end_at > ?'
        params.extend([end, start])
    elif start_at is not None or end_at is not None:
        raise ValueError(
            'Blackout filtering requires both start_at and end_at.'
        )
    sql += ' ORDER BY start_at,end_at,id'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_blackout_from_row(row) for row in rows]


def assign_service_resource(
    organization_slug: str,
    *,
    service_id: int,
    resource_id: int,
) -> None:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    service = scheduling_calendars.get_service_type(
        organization_slug, service_id
    )
    resource = _active_resource(organization_slug, resource_id)
    if service is None or service.status == 'archived':
        raise PermissionError('Scheduling service is unavailable.')
    if service.calendar_id != resource.calendar_id:
        raise PermissionError(
            'Scheduling service and resource must share a calendar.'
        )
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            INSERT OR IGNORE INTO scheduling_service_resources(
                organization_id,service_id,resource_id,created_at
            ) VALUES(?,?,?,?)
            ''',
            (
                organization_id,
                service.id,
                resource.id,
                tenant_auth.now(),
            ),
        )
        conn.commit()


def list_service_resources(
    organization_slug: str,
    service_id: int,
) -> list[SchedulingResource]:
    ensure_schema()
    organization_id = _organization_id(organization_slug)
    service = scheduling_calendars.get_service_type(
        organization_slug, service_id
    )
    if service is None:
        return []
    with tenant_auth.db() as conn:
        rows = conn.execute(
            '''
            SELECT r.*,o.slug AS organization_slug,c.slug AS calendar_slug
            FROM scheduling_service_resources sr
            JOIN scheduling_resources r
              ON r.id=sr.resource_id
             AND r.organization_id=sr.organization_id
            JOIN auth_organizations o ON o.id=r.organization_id
            JOIN scheduling_calendars c
              ON c.id=r.calendar_id
             AND c.organization_id=r.organization_id
            WHERE sr.organization_id=?
              AND sr.service_id=?
              AND r.status='active'
            ORDER BY r.name COLLATE NOCASE,r.id
            ''',
            (organization_id, service.id),
        ).fetchall()
    return [_resource_from_row(row) for row in rows]


def _staff_user_id(
    organization_slug: str,
    user_id: int | None,
    kind: str,
) -> int | None:
    if kind != 'staff':
        if user_id is not None:
            raise ValueError(
                'Only staff resources may reference a user account.'
            )
        return None
    if user_id is None:
        raise ValueError('Staff resources require a user account.')
    clean_user_id = _positive_int(user_id, 'user_id')
    membership = tenant_memberships.get_membership(
        clean_user_id, organization_slug
    )
    if (
        membership is None
        or membership.status != 'active'
        or membership.role not in {'owner', 'admin', 'staff'}
    ):
        raise PermissionError(
            'Staff resource user must be active staff in this tenant.'
        )
    return clean_user_id


def _active_resource(
    organization_slug: str,
    resource_id: int,
) -> SchedulingResource:
    resource = get_resource(organization_slug, resource_id)
    if resource is None or resource.status != 'active':
        raise PermissionError('Scheduling resource is unavailable.')
    return resource


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


def _resource_row(conn, organization_id: int, resource_id: int):
    return conn.execute(
        '''
        SELECT r.*,o.slug AS organization_slug,c.slug AS calendar_slug
        FROM scheduling_resources r
        JOIN auth_organizations o ON o.id=r.organization_id
        JOIN scheduling_calendars c
          ON c.id=r.calendar_id AND c.organization_id=r.organization_id
        WHERE r.organization_id=? AND r.id=?
        LIMIT 1
        ''',
        (organization_id, resource_id),
    ).fetchone()


def _slug(value: str) -> str:
    clean = (value or '').strip().lower()
    if (
        not clean
        or len(clean) > 100
        or not _SLUG_RE.fullmatch(clean)
    ):
        raise ValueError('Resource slug is invalid.')
    return clean


def _name(value: str) -> str:
    clean = (value or '').strip()
    if not clean or len(clean) > 200:
        raise ValueError(
            'Resource name must be 1 to 200 characters.'
        )
    return clean


def _kind(value: str) -> str:
    clean = (value or '').strip().lower()
    if clean not in RESOURCE_KINDS:
        raise ValueError(f'Unknown scheduling resource kind: {clean}')
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


def _resource_from_row(row) -> SchedulingResource:
    return SchedulingResource(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        calendar_id=int(row['calendar_id']),
        calendar_slug=str(row['calendar_slug']),
        user_id=(
            int(row['user_id']) if row['user_id'] is not None else None
        ),
        slug=str(row['slug']),
        name=str(row['name']),
        kind=str(row['kind']),
        status=str(row['status']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )


def _availability_from_row(row) -> WeeklyAvailability:
    return WeeklyAvailability(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        resource_id=int(row['resource_id']),
        weekday=int(row['weekday']),
        start_minute=int(row['start_minute']),
        end_minute=int(row['end_minute']),
        created_at=int(row['created_at']),
    )


def _blackout_from_row(row) -> BlackoutPeriod:
    return BlackoutPeriod(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        resource_id=int(row['resource_id']),
        start_at=int(row['start_at']),
        end_at=int(row['end_at']),
        reason=str(row['reason']),
        created_at=int(row['created_at']),
    )
