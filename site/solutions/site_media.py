from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3
from urllib.parse import urlsplit

import tenant_auth
import tenant_sites


MEDIA_STATUSES = ('draft', 'published', 'archived')
MEDIA_KINDS = ('image', 'video', 'audio', 'document')
_SLUG_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


@dataclass(frozen=True)
class MediaReference:
    id: int
    site_id: int
    organization_slug: str
    site_slug: str
    slug: str
    kind: str
    source: str
    alt_text: str
    mime_type: str
    status: str
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    tenant_sites.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS site_builder_media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                slug TEXT NOT NULL,
                kind TEXT NOT NULL,
                source TEXT NOT NULL,
                alt_text TEXT NOT NULL DEFAULT '',
                mime_type TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(site_id, slug),
                CHECK(kind IN ('image', 'video', 'audio', 'document')),
                CHECK(status IN ('draft', 'published', 'archived')),
                FOREIGN KEY(site_id)
                    REFERENCES site_builder_sites(id) ON DELETE CASCADE
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_site_builder_media_site_status '
            'ON site_builder_media(site_id, status, id)'
        )
        conn.commit()


def _site(organization_slug: str, site_slug: str):
    return tenant_sites.get_site(organization_slug, site_slug)


def _slug(value: str) -> str:
    value = (value or '').strip().lower()
    if not value or not _SLUG_RE.fullmatch(value):
        raise ValueError(
            'Media slug must contain lowercase letters/numbers separated by hyphens.'
        )
    return value


def _kind(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in MEDIA_KINDS:
        raise ValueError(f'Unsupported media kind: {value}')
    return value


def _status(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in MEDIA_STATUSES:
        raise ValueError(f'Unknown media status: {value}')
    return value


def _source(value: str) -> str:
    value = (value or '').strip()
    if not value:
        raise ValueError('Media source is required.')
    if value.startswith('/'):
        if value.startswith('//'):
            raise ValueError('Protocol-relative media sources are not allowed.')
        return value
    parsed = urlsplit(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise ValueError(
            'Media source must be a root-relative path or an http/https URL.'
        )
    return value


def _mime_type(value: str) -> str:
    value = (value or '').strip().lower()
    if value and ('/' not in value or value.startswith('/') or value.endswith('/')):
        raise ValueError('Media MIME type must use type/subtype format.')
    return value


def create_media(
    organization_slug: str,
    site_slug: str,
    *,
    slug: str,
    kind: str,
    source: str,
    alt_text: str = '',
    mime_type: str = '',
    status: str = 'draft',
) -> MediaReference:
    site = _site(organization_slug, site_slug)
    if not site:
        raise ValueError('Site not found.')
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')

    ensure_schema()
    timestamp = tenant_auth.now()
    try:
        with tenant_auth.db() as conn:
            cursor = conn.execute(
                '''
                INSERT INTO site_builder_media(
                    site_id, slug, kind, source, alt_text, mime_type, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    site.id,
                    _slug(slug),
                    _kind(kind),
                    _source(source),
                    alt_text or '',
                    _mime_type(mime_type),
                    _status(status),
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
            row = _select(conn, site.id, int(cursor.lastrowid))
    except sqlite3.IntegrityError as exc:
        raise ValueError(
            'A media reference with that slug already exists for this site.'
        ) from exc
    return _from_row(row)


def get_media(
    organization_slug: str,
    site_slug: str,
    media_slug: str,
) -> MediaReference | None:
    site = _site(organization_slug, site_slug)
    if not site:
        return None
    ensure_schema()
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''
            SELECT m.*, o.slug AS organization_slug, s.slug AS site_slug
            FROM site_builder_media m
            JOIN site_builder_sites s ON s.id = m.site_id
            JOIN auth_organizations o ON o.id = s.organization_id
            WHERE m.site_id = ? AND m.slug = ?
            LIMIT 1
            ''',
            (site.id, (media_slug or '').strip().lower()),
        ).fetchone()
    return _from_row(row) if row else None


def list_media(
    organization_slug: str,
    site_slug: str,
    *,
    published_only: bool = False,
    include_archived: bool = False,
    kind: str | None = None,
) -> list[MediaReference]:
    site = _site(organization_slug, site_slug)
    if not site:
        return []
    ensure_schema()
    sql = '''
        SELECT m.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM site_builder_media m
        JOIN site_builder_sites s ON s.id = m.site_id
        JOIN auth_organizations o ON o.id = s.organization_id
        WHERE m.site_id = ?
    '''
    params: list[object] = [site.id]
    if published_only:
        sql += " AND m.status = 'published'"
    elif not include_archived:
        sql += " AND m.status != 'archived'"
    if kind is not None:
        sql += ' AND m.kind = ?'
        params.append(_kind(kind))
    sql += ' ORDER BY m.id'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_from_row(row) for row in rows]


def update_media(
    organization_slug: str,
    site_slug: str,
    media_slug: str,
    *,
    kind: str | None = None,
    source: str | None = None,
    alt_text: str | None = None,
    mime_type: str | None = None,
    status: str | None = None,
) -> MediaReference | None:
    site = _site(organization_slug, site_slug)
    if not site:
        return None
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')
    existing = get_media(organization_slug, site_slug, media_slug)
    if not existing:
        return None
    if existing.status == 'archived':
        raise ValueError('Archived media references cannot be updated.')

    assignments: list[str] = []
    params: list[object] = []
    if kind is not None:
        assignments.append('kind = ?')
        params.append(_kind(kind))
    if source is not None:
        assignments.append('source = ?')
        params.append(_source(source))
    if alt_text is not None:
        assignments.append('alt_text = ?')
        params.append(alt_text)
    if mime_type is not None:
        assignments.append('mime_type = ?')
        params.append(_mime_type(mime_type))
    if status is not None:
        assignments.append('status = ?')
        params.append(_status(status))
    if not assignments:
        return existing

    assignments.append('updated_at = ?')
    params.append(tenant_auth.now())
    params.extend([site.id, existing.id])
    with tenant_auth.db() as conn:
        conn.execute(
            f'''
            UPDATE site_builder_media
            SET {', '.join(assignments)}
            WHERE site_id = ? AND id = ?
            ''',
            params,
        )
        conn.commit()
        row = _select(conn, site.id, existing.id)
    return _from_row(row)


def archive_media(
    organization_slug: str,
    site_slug: str,
    media_slug: str,
) -> MediaReference | None:
    existing = get_media(organization_slug, site_slug, media_slug)
    if not existing:
        return None
    if existing.status == 'archived':
        return existing
    return update_media(
        organization_slug,
        site_slug,
        media_slug,
        status='archived',
    )


def _select(conn, site_id: int, media_id: int):
    return conn.execute(
        '''
        SELECT m.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM site_builder_media m
        JOIN site_builder_sites s ON s.id = m.site_id
        JOIN auth_organizations o ON o.id = s.organization_id
        WHERE m.site_id = ? AND m.id = ?
        LIMIT 1
        ''',
        (site_id, media_id),
    ).fetchone()


def _from_row(row) -> MediaReference:
    return MediaReference(
        id=int(row['id']),
        site_id=int(row['site_id']),
        organization_slug=str(row['organization_slug']),
        site_slug=str(row['site_slug']),
        slug=str(row['slug']),
        kind=str(row['kind']),
        source=str(row['source']),
        alt_text=str(row['alt_text']),
        mime_type=str(row['mime_type']),
        status=str(row['status']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
