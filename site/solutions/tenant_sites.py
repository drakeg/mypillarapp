from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3

import tenant_auth


SITE_STATUSES = ('draft', 'published', 'archived')
_SLUG_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


@dataclass(frozen=True)
class Site:
    id: int
    organization_id: int
    organization_slug: str
    slug: str
    name: str
    status: str
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS site_builder_sites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                slug TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(organization_id, slug),
                CHECK(status IN ('draft', 'published', 'archived')),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_site_builder_sites_org_status '
            'ON site_builder_sites(organization_id, status)'
        )
        _seed_initial_sites(conn)
        conn.commit()


def _seed_initial_sites(conn: sqlite3.Connection) -> None:
    timestamp = tenant_auth.now()
    rows = conn.execute(
        "SELECT id, slug, name FROM auth_organizations WHERE status = 'active'"
    ).fetchall()
    for row in rows:
        conn.execute(
            '''
            INSERT OR IGNORE INTO site_builder_sites(
                organization_id, slug, name, status, created_at, updated_at
            ) VALUES (?, 'main', ?, 'draft', ?, ?)
            ''',
            (row['id'], row['name'], timestamp, timestamp),
        )


def _organization_id(conn: sqlite3.Connection, organization_slug: str) -> int | None:
    row = conn.execute(
        'SELECT id FROM auth_organizations WHERE slug = ?',
        ((organization_slug or '').strip().lower(),),
    ).fetchone()
    return int(row['id']) if row else None


def _normalize_slug(value: str) -> str:
    return (value or '').strip().lower()


def _validate_site_input(slug: str, name: str) -> tuple[str, str]:
    normalized_slug = _normalize_slug(slug)
    normalized_name = (name or '').strip()
    if not normalized_slug or not _SLUG_RE.fullmatch(normalized_slug):
        raise ValueError(
            'Site slug must contain lowercase letters/numbers separated by hyphens.'
        )
    if not normalized_name:
        raise ValueError('Site name is required.')
    return normalized_slug, normalized_name


def create_site(
    organization_slug: str,
    *,
    slug: str,
    name: str,
    status: str = 'draft',
) -> Site:
    ensure_schema()
    normalized_slug, normalized_name = _validate_site_input(slug, name)
    normalized_status = (status or '').strip().lower()
    if normalized_status not in SITE_STATUSES:
        raise ValueError(f'Unknown site status: {normalized_status}')

    with tenant_auth.db() as conn:
        organization_id = _organization_id(conn, organization_slug)
        if organization_id is None:
            raise ValueError('Organization not found.')
        timestamp = tenant_auth.now()
        try:
            cursor = conn.execute(
                '''
                INSERT INTO site_builder_sites(
                    organization_id, slug, name, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (
                    organization_id,
                    normalized_slug,
                    normalized_name,
                    normalized_status,
                    timestamp,
                    timestamp,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError('A site with that slug already exists for this organization.') from exc
        conn.commit()
        row = conn.execute(
            '''
            SELECT s.*, o.slug AS organization_slug
            FROM site_builder_sites s
            JOIN auth_organizations o ON o.id = s.organization_id
            WHERE s.id = ?
            ''',
            (cursor.lastrowid,),
        ).fetchone()
    return _site_from_row(row)


def get_site(organization_slug: str, site_slug: str) -> Site | None:
    ensure_schema()
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''
            SELECT s.*, o.slug AS organization_slug
            FROM site_builder_sites s
            JOIN auth_organizations o ON o.id = s.organization_id
            WHERE o.slug = ? AND s.slug = ?
            LIMIT 1
            ''',
            (
                (organization_slug or '').strip().lower(),
                _normalize_slug(site_slug),
            ),
        ).fetchone()
    return _site_from_row(row) if row else None


def list_sites(
    organization_slug: str,
    *,
    include_archived: bool = False,
) -> list[Site]:
    ensure_schema()
    sql = '''
        SELECT s.*, o.slug AS organization_slug
        FROM site_builder_sites s
        JOIN auth_organizations o ON o.id = s.organization_id
        WHERE o.slug = ?
    '''
    params: list[object] = [(organization_slug or '').strip().lower()]
    if not include_archived:
        sql += " AND s.status != 'archived'"
    sql += ' ORDER BY s.name COLLATE NOCASE, s.id'

    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_site_from_row(row) for row in rows]


def update_site(
    organization_slug: str,
    site_slug: str,
    *,
    name: str | None = None,
    status: str | None = None,
) -> Site | None:
    ensure_schema()
    assignments: list[str] = []
    params: list[object] = []

    if name is not None:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError('Site name is required.')
        assignments.append('name = ?')
        params.append(normalized_name)

    if status is not None:
        normalized_status = status.strip().lower()
        if normalized_status not in SITE_STATUSES:
            raise ValueError(f'Unknown site status: {normalized_status}')
        assignments.append('status = ?')
        params.append(normalized_status)

    if not assignments:
        return get_site(organization_slug, site_slug)

    assignments.append('updated_at = ?')
    params.append(tenant_auth.now())
    params.extend(
        [
            (organization_slug or '').strip().lower(),
            _normalize_slug(site_slug),
        ]
    )

    with tenant_auth.db() as conn:
        cursor = conn.execute(
            f'''
            UPDATE site_builder_sites
            SET {', '.join(assignments)}
            WHERE organization_id = (
                SELECT id FROM auth_organizations WHERE slug = ?
            )
              AND slug = ?
            ''',
            params,
        )
        conn.commit()
    if cursor.rowcount == 0:
        return None
    return get_site(organization_slug, site_slug)


def archive_site(organization_slug: str, site_slug: str) -> Site | None:
    return update_site(organization_slug, site_slug, status='archived')


def _site_from_row(row: sqlite3.Row) -> Site:
    return Site(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        slug=str(row['slug']),
        name=str(row['name']),
        status=str(row['status']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
