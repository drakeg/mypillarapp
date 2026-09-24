from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3

import tenant_auth
import tenant_sites


SERVICE_STATUSES = ('draft', 'published', 'archived')
_SLUG_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


@dataclass(frozen=True)
class Service:
    id: int
    site_id: int
    organization_slug: str
    site_slug: str
    slug: str
    name: str
    summary: str
    price_text: str
    status: str
    position: int
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    tenant_sites.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS site_builder_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                slug TEXT NOT NULL,
                name TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                price_text TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                position INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(site_id, slug),
                CHECK(status IN ('draft', 'published', 'archived')),
                FOREIGN KEY(site_id)
                    REFERENCES site_builder_sites(id) ON DELETE CASCADE
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_site_builder_services_site_status_position '
            'ON site_builder_services(site_id, status, position, id)'
        )
        conn.commit()


def _site(organization_slug: str, site_slug: str):
    return tenant_sites.get_site(organization_slug, site_slug)


def _slug(value: str) -> str:
    value = (value or '').strip().lower()
    if not value or not _SLUG_RE.fullmatch(value):
        raise ValueError(
            'Service slug must contain lowercase letters/numbers separated by hyphens.'
        )
    return value


def _status(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in SERVICE_STATUSES:
        raise ValueError(f'Unknown service status: {value}')
    return value


def _position(value: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Service position must be an integer.') from exc
    if value < 0:
        raise ValueError('Service position cannot be negative.')
    return value


def create_service(
    organization_slug: str,
    site_slug: str,
    *,
    slug: str,
    name: str,
    summary: str = '',
    price_text: str = '',
    status: str = 'draft',
    position: int = 0,
) -> Service:
    site = _site(organization_slug, site_slug)
    if not site:
        raise ValueError('Site not found.')
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')

    clean_name = (name or '').strip()
    if not clean_name:
        raise ValueError('Service name is required.')

    ensure_schema()
    timestamp = tenant_auth.now()
    try:
        with tenant_auth.db() as conn:
            cursor = conn.execute(
                '''
                INSERT INTO site_builder_services(
                    site_id, slug, name, summary, price_text, status, position,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    site.id,
                    _slug(slug),
                    clean_name,
                    summary or '',
                    price_text or '',
                    _status(status),
                    _position(position),
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
            row = _select(conn, site.id, int(cursor.lastrowid))
    except sqlite3.IntegrityError as exc:
        raise ValueError(
            'A service with that slug already exists for this site.'
        ) from exc
    return _from_row(row)


def get_service(
    organization_slug: str,
    site_slug: str,
    service_slug: str,
) -> Service | None:
    site = _site(organization_slug, site_slug)
    if not site:
        return None
    ensure_schema()
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''
            SELECT v.*, o.slug AS organization_slug, s.slug AS site_slug
            FROM site_builder_services v
            JOIN site_builder_sites s ON s.id = v.site_id
            JOIN auth_organizations o ON o.id = s.organization_id
            WHERE v.site_id = ? AND v.slug = ?
            LIMIT 1
            ''',
            (site.id, (service_slug or '').strip().lower()),
        ).fetchone()
    return _from_row(row) if row else None


def list_services(
    organization_slug: str,
    site_slug: str,
    *,
    published_only: bool = False,
    include_archived: bool = False,
) -> list[Service]:
    site = _site(organization_slug, site_slug)
    if not site:
        return []
    ensure_schema()
    sql = '''
        SELECT v.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM site_builder_services v
        JOIN site_builder_sites s ON s.id = v.site_id
        JOIN auth_organizations o ON o.id = s.organization_id
        WHERE v.site_id = ?
    '''
    params: list[object] = [site.id]
    if published_only:
        sql += " AND v.status = 'published'"
    elif not include_archived:
        sql += " AND v.status != 'archived'"
    sql += ' ORDER BY v.position, v.id'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_from_row(row) for row in rows]


def update_service(
    organization_slug: str,
    site_slug: str,
    service_slug: str,
    *,
    name: str | None = None,
    summary: str | None = None,
    price_text: str | None = None,
    status: str | None = None,
    position: int | None = None,
) -> Service | None:
    site = _site(organization_slug, site_slug)
    if not site:
        return None
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')
    existing = get_service(organization_slug, site_slug, service_slug)
    if not existing:
        return None
    if existing.status == 'archived':
        raise ValueError('Archived services cannot be updated.')

    assignments: list[str] = []
    params: list[object] = []
    if name is not None:
        clean = name.strip()
        if not clean:
            raise ValueError('Service name is required.')
        assignments.append('name = ?')
        params.append(clean)
    if summary is not None:
        assignments.append('summary = ?')
        params.append(summary)
    if price_text is not None:
        assignments.append('price_text = ?')
        params.append(price_text)
    if status is not None:
        assignments.append('status = ?')
        params.append(_status(status))
    if position is not None:
        assignments.append('position = ?')
        params.append(_position(position))
    if not assignments:
        return existing

    assignments.append('updated_at = ?')
    params.append(tenant_auth.now())
    params.extend([site.id, existing.id])
    with tenant_auth.db() as conn:
        conn.execute(
            f'''
            UPDATE site_builder_services
            SET {', '.join(assignments)}
            WHERE site_id = ? AND id = ?
            ''',
            params,
        )
        conn.commit()
        row = _select(conn, site.id, existing.id)
    return _from_row(row)


def archive_service(
    organization_slug: str,
    site_slug: str,
    service_slug: str,
) -> Service | None:
    existing = get_service(organization_slug, site_slug, service_slug)
    if not existing:
        return None
    if existing.status == 'archived':
        return existing
    return update_service(
        organization_slug,
        site_slug,
        service_slug,
        status='archived',
    )


def _select(conn, site_id: int, service_id: int):
    return conn.execute(
        '''
        SELECT v.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM site_builder_services v
        JOIN site_builder_sites s ON s.id = v.site_id
        JOIN auth_organizations o ON o.id = s.organization_id
        WHERE v.site_id = ? AND v.id = ?
        LIMIT 1
        ''',
        (site_id, service_id),
    ).fetchone()


def _from_row(row) -> Service:
    return Service(
        id=int(row['id']),
        site_id=int(row['site_id']),
        organization_slug=str(row['organization_slug']),
        site_slug=str(row['site_slug']),
        slug=str(row['slug']),
        name=str(row['name']),
        summary=str(row['summary']),
        price_text=str(row['price_text']),
        status=str(row['status']),
        position=int(row['position']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
