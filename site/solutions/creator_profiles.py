from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from urllib.parse import urlsplit

import tenant_auth
import tenant_sites


PROFILE_STATUSES = ('draft', 'published', 'archived')
LINK_STATUSES = ('draft', 'published', 'archived')


@dataclass(frozen=True)
class CreatorProfile:
    site_id: int
    organization_slug: str
    site_slug: str
    display_name: str
    bio: str
    avatar_url: str
    status: str
    created_at: int
    updated_at: int


@dataclass(frozen=True)
class CreatorLink:
    id: int
    site_id: int
    organization_slug: str
    site_slug: str
    label: str
    target: str
    position: int
    status: str
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    tenant_sites.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS creator_profiles (
                site_id INTEGER PRIMARY KEY,
                display_name TEXT NOT NULL,
                bio TEXT NOT NULL DEFAULT '',
                avatar_url TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                CHECK(status IN ('draft','published','archived')),
                FOREIGN KEY(site_id)
                    REFERENCES site_builder_sites(id) ON DELETE CASCADE
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS creator_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                target TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                CHECK(status IN ('draft','published','archived')),
                FOREIGN KEY(site_id)
                    REFERENCES site_builder_sites(id) ON DELETE CASCADE
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_creator_links_site_status_position '
            'ON creator_links(site_id, status, position, id)'
        )
        conn.commit()


def _site(organization_slug: str, site_slug: str):
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        raise ValueError('Site not found.')
    return site


def _clean_status(value: str, allowed: tuple[str, ...]) -> str:
    clean = (value or '').strip().lower()
    if clean not in allowed:
        raise ValueError(f'Unknown creator status: {clean}')
    return clean


def _clean_text(value: str, *, field: str, limit: int, required: bool = False) -> str:
    clean = (value or '').strip()
    if required and not clean:
        raise ValueError(f'{field} is required.')
    if len(clean) > limit:
        raise ValueError(f'{field} must be {limit} characters or fewer.')
    return clean


def _clean_position(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError('Link position must be an integer.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Link position must be an integer.') from exc
    if clean < 0:
        raise ValueError('Link position cannot be negative.')
    return clean


def _clean_external_url(value: str, *, field: str, allow_empty: bool = False) -> str:
    clean = (value or '').strip()
    if not clean and allow_empty:
        return ''
    parsed = urlsplit(clean)
    if (
        parsed.scheme.lower() != 'https'
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(f'{field} must use a credential-free HTTPS URL.')
    return clean


def _clean_link_target(value: str) -> str:
    clean = (value or '').strip()
    if not clean:
        raise ValueError('Link target is required.')
    if clean.startswith('/'):
        if clean.startswith('//'):
            raise ValueError(
                'Internal link targets must be root-relative paths.'
            )
        return clean
    return _clean_external_url(clean, field='External link target')


def upsert_profile(
    organization_slug: str,
    site_slug: str,
    *,
    display_name: str,
    bio: str = '',
    avatar_url: str = '',
    status: str = 'draft',
) -> CreatorProfile:
    site = _site(organization_slug, site_slug)
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')

    display_name = _clean_text(
        display_name, field='Display name', limit=160, required=True
    )
    bio = _clean_text(bio, field='Bio', limit=4000)
    avatar_url = _clean_external_url(
        avatar_url, field='Avatar URL', allow_empty=True
    )
    status = _clean_status(status, PROFILE_STATUSES)
    ensure_schema()
    now = tenant_auth.now()

    with tenant_auth.db() as conn:
        existing = conn.execute(
            'SELECT created_at, status FROM creator_profiles WHERE site_id=?',
            (site.id,),
        ).fetchone()
        if existing is not None and existing['status'] == 'archived':
            raise ValueError('Archived creator profiles cannot be updated.')
        created_at = int(existing['created_at']) if existing else now
        conn.execute(
            '''
            INSERT INTO creator_profiles(
                site_id, display_name, bio, avatar_url, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(site_id) DO UPDATE SET
                display_name=excluded.display_name,
                bio=excluded.bio,
                avatar_url=excluded.avatar_url,
                status=excluded.status,
                updated_at=excluded.updated_at
            ''',
            (
                site.id, display_name, bio, avatar_url, status,
                created_at, now,
            ),
        )
        conn.commit()
        row = _select_profile(conn, site.id)
    return _profile_from_row(row)


def get_profile(
    organization_slug: str,
    site_slug: str,
    *,
    published_only: bool = False,
) -> CreatorProfile | None:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        return None
    ensure_schema()
    with tenant_auth.db() as conn:
        row = _select_profile(conn, site.id)
    if row is None:
        return None
    profile = _profile_from_row(row)
    if published_only and profile.status != 'published':
        return None
    if profile.status == 'archived' and not published_only:
        return profile
    return profile


def archive_profile(
    organization_slug: str,
    site_slug: str,
) -> CreatorProfile | None:
    existing = get_profile(organization_slug, site_slug)
    if existing is None:
        return None
    if existing.status == 'archived':
        return existing
    return upsert_profile(
        organization_slug,
        site_slug,
        display_name=existing.display_name,
        bio=existing.bio,
        avatar_url=existing.avatar_url,
        status='archived',
    )


def create_link(
    organization_slug: str,
    site_slug: str,
    *,
    label: str,
    target: str,
    position: int = 0,
    status: str = 'draft',
) -> CreatorLink:
    site = _site(organization_slug, site_slug)
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')

    ensure_schema()
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        cursor = conn.execute(
            '''
            INSERT INTO creator_links(
                site_id, label, target, position, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                site.id,
                _clean_text(label, field='Link label', limit=160, required=True),
                _clean_link_target(target),
                _clean_position(position),
                _clean_status(status, LINK_STATUSES),
                now,
                now,
            ),
        )
        conn.commit()
        row = _select_link(conn, site.id, int(cursor.lastrowid))
    return _link_from_row(row)


def get_link(
    organization_slug: str,
    site_slug: str,
    link_id: int,
) -> CreatorLink | None:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        return None
    ensure_schema()
    with tenant_auth.db() as conn:
        row = _select_link(conn, site.id, int(link_id))
    return _link_from_row(row) if row else None


def list_links(
    organization_slug: str,
    site_slug: str,
    *,
    published_only: bool = False,
    include_archived: bool = False,
) -> list[CreatorLink]:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        return []
    ensure_schema()
    sql = '''
        SELECT l.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM creator_links l
        JOIN site_builder_sites s ON s.id=l.site_id
        JOIN auth_organizations o ON o.id=s.organization_id
        WHERE l.site_id=?
    '''
    params: list[object] = [site.id]
    if published_only:
        sql += " AND l.status='published'"
    elif not include_archived:
        sql += " AND l.status!='archived'"
    sql += ' ORDER BY l.position, l.id'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_link_from_row(row) for row in rows]


def update_link(
    organization_slug: str,
    site_slug: str,
    link_id: int,
    *,
    label: str | None = None,
    target: str | None = None,
    position: int | None = None,
    status: str | None = None,
) -> CreatorLink | None:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        return None
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')

    existing = get_link(organization_slug, site_slug, link_id)
    if existing is None:
        return None
    if existing.status == 'archived':
        raise ValueError('Archived creator links cannot be updated.')

    assignments: list[str] = []
    params: list[object] = []
    if label is not None:
        assignments.append('label=?')
        params.append(
            _clean_text(label, field='Link label', limit=160, required=True)
        )
    if target is not None:
        assignments.append('target=?')
        params.append(_clean_link_target(target))
    if position is not None:
        assignments.append('position=?')
        params.append(_clean_position(position))
    if status is not None:
        assignments.append('status=?')
        params.append(_clean_status(status, LINK_STATUSES))
    if not assignments:
        return existing

    assignments.append('updated_at=?')
    params.append(tenant_auth.now())
    params.extend([site.id, int(link_id)])
    with tenant_auth.db() as conn:
        conn.execute(
            f'''
            UPDATE creator_links
            SET {', '.join(assignments)}
            WHERE site_id=? AND id=?
            ''',
            params,
        )
        conn.commit()
        row = _select_link(conn, site.id, int(link_id))
    return _link_from_row(row)


def archive_link(
    organization_slug: str,
    site_slug: str,
    link_id: int,
) -> CreatorLink | None:
    existing = get_link(organization_slug, site_slug, link_id)
    if existing is None:
        return None
    if existing.status == 'archived':
        return existing
    return update_link(
        organization_slug,
        site_slug,
        link_id,
        status='archived',
    )


def _select_profile(conn: sqlite3.Connection, site_id: int):
    return conn.execute(
        '''
        SELECT p.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM creator_profiles p
        JOIN site_builder_sites s ON s.id=p.site_id
        JOIN auth_organizations o ON o.id=s.organization_id
        WHERE p.site_id=?
        LIMIT 1
        ''',
        (site_id,),
    ).fetchone()


def _select_link(conn: sqlite3.Connection, site_id: int, link_id: int):
    return conn.execute(
        '''
        SELECT l.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM creator_links l
        JOIN site_builder_sites s ON s.id=l.site_id
        JOIN auth_organizations o ON o.id=s.organization_id
        WHERE l.site_id=? AND l.id=?
        LIMIT 1
        ''',
        (site_id, link_id),
    ).fetchone()


def _profile_from_row(row) -> CreatorProfile:
    return CreatorProfile(
        site_id=int(row['site_id']),
        organization_slug=str(row['organization_slug']),
        site_slug=str(row['site_slug']),
        display_name=str(row['display_name']),
        bio=str(row['bio']),
        avatar_url=str(row['avatar_url']),
        status=str(row['status']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )


def _link_from_row(row) -> CreatorLink:
    return CreatorLink(
        id=int(row['id']),
        site_id=int(row['site_id']),
        organization_slug=str(row['organization_slug']),
        site_slug=str(row['site_slug']),
        label=str(row['label']),
        target=str(row['target']),
        position=int(row['position']),
        status=str(row['status']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
