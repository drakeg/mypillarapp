from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from urllib.parse import urlparse

import tenant_auth
import tenant_sites


DOWNLOAD_STATUSES = ('draft', 'published', 'archived')
DOWNLOAD_VISIBILITIES = ('public', 'customer', 'internal')
DOWNLOAD_SOURCE_TYPES = ('external_url', 'storage_key')


@dataclass(frozen=True)
class DigitalDownload:
    id: int
    site_id: int
    organization_slug: str
    site_slug: str
    title: str
    description: str
    version: str
    source_type: str
    source_ref: str
    file_name: str
    mime_type: str
    visibility: str
    status: str
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    tenant_sites.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS creator_downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT '',
                source_type TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                file_name TEXT NOT NULL DEFAULT '',
                mime_type TEXT NOT NULL DEFAULT '',
                visibility TEXT NOT NULL DEFAULT 'public',
                status TEXT NOT NULL DEFAULT 'draft',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                CHECK(source_type IN ('external_url','storage_key')),
                CHECK(visibility IN ('public','customer','internal')),
                CHECK(status IN ('draft','published','archived')),
                FOREIGN KEY(site_id)
                    REFERENCES site_builder_sites(id) ON DELETE CASCADE
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_creator_downloads_site_status '
            'ON creator_downloads(site_id, status, visibility, id)'
        )
        conn.commit()


def _site(organization_slug: str, site_slug: str):
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        raise ValueError('Site not found.')
    return site


def _text(value: str, *, field: str, limit: int, required: bool = False) -> str:
    clean = (value or '').strip()
    if required and not clean:
        raise ValueError(f'{field} is required.')
    if len(clean) > limit:
        raise ValueError(f'{field} must be {limit} characters or fewer.')
    return clean


def _source_type(value: str) -> str:
    clean = (value or '').strip().lower()
    if clean not in DOWNLOAD_SOURCE_TYPES:
        raise ValueError(f'Unknown download source type: {clean}')
    return clean


def _source_ref(source_type: str, value: str) -> str:
    clean = (value or '').strip()
    if not clean:
        raise ValueError('Download source reference is required.')
    if len(clean) > 2048 or '\x00' in clean:
        raise ValueError('Download source reference is invalid.')
    if source_type == 'external_url':
        parsed = urlparse(clean)
        if parsed.scheme != 'https' or not parsed.netloc:
            raise ValueError('External download URL must use HTTPS.')
        if parsed.username or parsed.password:
            raise ValueError('External download URL cannot contain embedded credentials.')
        return clean
    if clean.startswith(('/', '\\')) or clean.lower().startswith('file:'):
        raise ValueError('Storage key cannot be a local filesystem path.')
    parts = clean.replace('\\', '/').split('/')
    if any(part in {'', '.', '..'} for part in parts):
        raise ValueError('Storage key contains an unsafe path segment.')
    return clean


def _status(value: str) -> str:
    clean = (value or '').strip().lower()
    if clean not in DOWNLOAD_STATUSES:
        raise ValueError(f'Unknown download status: {clean}')
    return clean


def _visibility(value: str) -> str:
    clean = (value or '').strip().lower()
    if clean not in DOWNLOAD_VISIBILITIES:
        raise ValueError(f'Unknown download visibility: {clean}')
    return clean


def create_download(
    organization_slug: str,
    site_slug: str,
    *,
    title: str,
    source_type: str,
    source_ref: str,
    description: str = '',
    version: str = '',
    file_name: str = '',
    mime_type: str = '',
    visibility: str = 'public',
    status: str = 'draft',
) -> DigitalDownload:
    site = _site(organization_slug, site_slug)
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')
    clean_source_type = _source_type(source_type)
    ensure_schema()
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        cur = conn.execute(
            '''
            INSERT INTO creator_downloads(
                site_id,title,description,version,source_type,source_ref,
                file_name,mime_type,visibility,status,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ''',
            (
                site.id,
                _text(title, field='Download title', limit=200, required=True),
                _text(description, field='Download description', limit=4000),
                _text(version, field='Download version', limit=100),
                clean_source_type,
                _source_ref(clean_source_type, source_ref),
                _text(file_name, field='File name', limit=255),
                _text(mime_type, field='MIME type', limit=200),
                _visibility(visibility),
                _status(status),
                now,
                now,
            ),
        )
        conn.commit()
        row = _select(conn, site.id, int(cur.lastrowid))
    return _from_row(row)


def get_download(organization_slug: str, site_slug: str, download_id: int) -> DigitalDownload | None:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        return None
    ensure_schema()
    with tenant_auth.db() as conn:
        row = _select(conn, site.id, int(download_id))
    return _from_row(row) if row else None


def list_downloads(
    organization_slug: str,
    site_slug: str,
    *,
    published_only: bool = False,
    visibility: str | None = None,
    include_archived: bool = False,
) -> list[DigitalDownload]:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        return []
    ensure_schema()
    sql = '''
        SELECT d.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM creator_downloads d
        JOIN site_builder_sites s ON s.id=d.site_id
        JOIN auth_organizations o ON o.id=s.organization_id
        WHERE d.site_id=?
    '''
    params: list[object] = [site.id]
    if published_only:
        sql += " AND d.status='published'"
    elif not include_archived:
        sql += " AND d.status!='archived'"
    if visibility is not None:
        sql += ' AND d.visibility=?'
        params.append(_visibility(visibility))
    sql += ' ORDER BY d.id'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_from_row(row) for row in rows]


def update_download(
    organization_slug: str,
    site_slug: str,
    download_id: int,
    **changes,
) -> DigitalDownload | None:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        return None
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')
    existing = get_download(organization_slug, site_slug, download_id)
    if existing is None:
        return None
    if existing.status == 'archived':
        raise ValueError('Archived downloads cannot be updated.')

    allowed = {'title','description','version','source_type','source_ref','file_name','mime_type','visibility','status'}
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f'Unknown download fields: {sorted(unknown)}')

    values = {
        'title': existing.title,
        'description': existing.description,
        'version': existing.version,
        'source_type': existing.source_type,
        'source_ref': existing.source_ref,
        'file_name': existing.file_name,
        'mime_type': existing.mime_type,
        'visibility': existing.visibility,
        'status': existing.status,
    }
    values.update(changes)
    clean_source_type = _source_type(values['source_type'])

    with tenant_auth.db() as conn:
        conn.execute(
            '''
            UPDATE creator_downloads
            SET title=?,description=?,version=?,source_type=?,source_ref=?,
                file_name=?,mime_type=?,visibility=?,status=?,updated_at=?
            WHERE site_id=? AND id=?
            ''',
            (
                _text(values['title'], field='Download title', limit=200, required=True),
                _text(values['description'], field='Download description', limit=4000),
                _text(values['version'], field='Download version', limit=100),
                clean_source_type,
                _source_ref(clean_source_type, values['source_ref']),
                _text(values['file_name'], field='File name', limit=255),
                _text(values['mime_type'], field='MIME type', limit=200),
                _visibility(values['visibility']),
                _status(values['status']),
                tenant_auth.now(),
                site.id,
                int(download_id),
            ),
        )
        conn.commit()
        row = _select(conn, site.id, int(download_id))
    return _from_row(row)


def archive_download(organization_slug: str, site_slug: str, download_id: int) -> DigitalDownload | None:
    existing = get_download(organization_slug, site_slug, download_id)
    if existing is None or existing.status == 'archived':
        return existing
    return update_download(
        organization_slug, site_slug, download_id, status='archived'
    )


def public_source(download: DigitalDownload) -> str | None:
    if download.status != 'published' or download.visibility != 'public':
        return None
    if download.source_type != 'external_url':
        return None
    return download.source_ref


def _select(conn: sqlite3.Connection, site_id: int, download_id: int):
    return conn.execute(
        '''
        SELECT d.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM creator_downloads d
        JOIN site_builder_sites s ON s.id=d.site_id
        JOIN auth_organizations o ON o.id=s.organization_id
        WHERE d.site_id=? AND d.id=?
        LIMIT 1
        ''',
        (site_id, download_id),
    ).fetchone()


def _from_row(row) -> DigitalDownload:
    return DigitalDownload(
        id=int(row['id']),
        site_id=int(row['site_id']),
        organization_slug=str(row['organization_slug']),
        site_slug=str(row['site_slug']),
        title=str(row['title']),
        description=str(row['description']),
        version=str(row['version']),
        source_type=str(row['source_type']),
        source_ref=str(row['source_ref']),
        file_name=str(row['file_name']),
        mime_type=str(row['mime_type']),
        visibility=str(row['visibility']),
        status=str(row['status']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
