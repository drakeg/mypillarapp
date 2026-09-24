from __future__ import annotations

from dataclasses import dataclass
import re

import tenant_auth
import tenant_sites


PAGE_STATUSES = ('draft', 'published', 'archived')
_SLUG_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


@dataclass(frozen=True)
class Page:
    id: int
    site_id: int
    organization_slug: str
    site_slug: str
    slug: str
    title: str
    summary: str
    body: str
    status: str
    position: int
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    tenant_sites.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS site_builder_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                slug TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
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
            'CREATE INDEX IF NOT EXISTS idx_site_builder_pages_site_status_position '
            'ON site_builder_pages(site_id, status, position, id)'
        )
        conn.commit()


def _normalize_slug(value: str) -> str:
    return (value or '').strip().lower()


def _normalize_text(value: str) -> str:
    return (value or '').strip()


def _validate_slug(slug: str) -> str:
    normalized = _normalize_slug(slug)
    if not normalized or not _SLUG_RE.fullmatch(normalized):
        raise ValueError(
            'Page slug must contain lowercase letters/numbers separated by hyphens.'
        )
    return normalized


def _validate_position(position: int) -> int:
    try:
        normalized = int(position)
    except (TypeError, ValueError) as exc:
        raise ValueError('Page position must be an integer.') from exc
    if normalized < 0:
        raise ValueError('Page position cannot be negative.')
    return normalized


def _validate_status(status: str) -> str:
    normalized = (status or '').strip().lower()
    if normalized not in PAGE_STATUSES:
        raise ValueError(f'Unknown page status: {normalized}')
    return normalized


def _site(organization_slug: str, site_slug: str):
    return tenant_sites.get_site(organization_slug, site_slug)


def create_page(
    organization_slug: str,
    site_slug: str,
    *,
    slug: str,
    title: str,
    summary: str = '',
    body: str = '',
    status: str = 'draft',
    position: int = 0,
) -> Page:
    site = _site(organization_slug, site_slug)
    if not site:
        raise ValueError('Site not found.')
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')

    normalized_slug = _validate_slug(slug)
    clean_title = _normalize_text(title)
    if not clean_title:
        raise ValueError('Page title is required.')
    clean_status = _validate_status(status)
    clean_position = _validate_position(position)

    ensure_schema()
    timestamp = tenant_auth.now()
    with tenant_auth.db() as conn:
        try:
            cursor = conn.execute(
                '''
                INSERT INTO site_builder_pages(
                    site_id, slug, title, summary, body, status, position,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    site.id,
                    normalized_slug,
                    clean_title,
                    summary or '',
                    body or '',
                    clean_status,
                    clean_position,
                    timestamp,
                    timestamp,
                ),
            )
        except Exception as exc:
            if 'UNIQUE constraint failed' in str(exc):
                raise ValueError(
                    'A page with that slug already exists for this site.'
                ) from exc
            raise
        conn.commit()
        row = _select_page(conn, site.id, int(cursor.lastrowid))
    return _page_from_row(row)


def get_page(
    organization_slug: str,
    site_slug: str,
    page_slug: str,
) -> Page | None:
    site = _site(organization_slug, site_slug)
    if not site:
        return None
    ensure_schema()
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''
            SELECT p.*, o.slug AS organization_slug, s.slug AS site_slug
            FROM site_builder_pages p
            JOIN site_builder_sites s ON s.id = p.site_id
            JOIN auth_organizations o ON o.id = s.organization_id
            WHERE p.site_id = ? AND p.slug = ?
            LIMIT 1
            ''',
            (site.id, _normalize_slug(page_slug)),
        ).fetchone()
    return _page_from_row(row) if row else None


def list_pages(
    organization_slug: str,
    site_slug: str,
    *,
    published_only: bool = False,
    include_archived: bool = False,
) -> list[Page]:
    site = _site(organization_slug, site_slug)
    if not site:
        return []
    ensure_schema()
    sql = '''
        SELECT p.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM site_builder_pages p
        JOIN site_builder_sites s ON s.id = p.site_id
        JOIN auth_organizations o ON o.id = s.organization_id
        WHERE p.site_id = ?
    '''
    params: list[object] = [site.id]
    if published_only:
        sql += " AND p.status = 'published'"
    elif not include_archived:
        sql += " AND p.status != 'archived'"
    sql += ' ORDER BY p.position, p.id'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_page_from_row(row) for row in rows]


def update_page(
    organization_slug: str,
    site_slug: str,
    page_slug: str,
    *,
    title: str | None = None,
    summary: str | None = None,
    body: str | None = None,
    status: str | None = None,
    position: int | None = None,
) -> Page | None:
    site = _site(organization_slug, site_slug)
    if not site:
        return None
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')

    existing = get_page(organization_slug, site_slug, page_slug)
    if not existing:
        return None
    if existing.status == 'archived':
        raise ValueError('Archived pages cannot be updated.')

    assignments: list[str] = []
    params: list[object] = []

    if title is not None:
        clean_title = _normalize_text(title)
        if not clean_title:
            raise ValueError('Page title is required.')
        assignments.append('title = ?')
        params.append(clean_title)
    if summary is not None:
        assignments.append('summary = ?')
        params.append(summary)
    if body is not None:
        assignments.append('body = ?')
        params.append(body)
    if status is not None:
        assignments.append('status = ?')
        params.append(_validate_status(status))
    if position is not None:
        assignments.append('position = ?')
        params.append(_validate_position(position))

    if not assignments:
        return existing

    assignments.append('updated_at = ?')
    params.append(tenant_auth.now())
    params.extend([site.id, existing.id])

    ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            f'''
            UPDATE site_builder_pages
            SET {', '.join(assignments)}
            WHERE site_id = ? AND id = ?
            ''',
            params,
        )
        conn.commit()
        row = _select_page(conn, site.id, existing.id)
    return _page_from_row(row)


def archive_page(
    organization_slug: str,
    site_slug: str,
    page_slug: str,
) -> Page | None:
    page = get_page(organization_slug, site_slug, page_slug)
    if not page:
        return None
    if page.status == 'archived':
        return page
    return update_page(
        organization_slug,
        site_slug,
        page_slug,
        status='archived',
    )


def _select_page(conn, site_id: int, page_id: int):
    return conn.execute(
        '''
        SELECT p.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM site_builder_pages p
        JOIN site_builder_sites s ON s.id = p.site_id
        JOIN auth_organizations o ON o.id = s.organization_id
        WHERE p.site_id = ? AND p.id = ?
        LIMIT 1
        ''',
        (site_id, int(page_id)),
    ).fetchone()


def _page_from_row(row) -> Page:
    return Page(
        id=int(row['id']),
        site_id=int(row['site_id']),
        organization_slug=str(row['organization_slug']),
        site_slug=str(row['site_slug']),
        slug=str(row['slug']),
        title=str(row['title']),
        summary=str(row['summary']),
        body=str(row['body']),
        status=str(row['status']),
        position=int(row['position']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
