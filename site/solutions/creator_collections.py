from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3
from urllib.parse import urlsplit

import tenant_auth
import tenant_sites


COLLECTION_STATUSES = ('draft', 'published', 'archived')
_SLUG_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


@dataclass(frozen=True)
class ContentCollection:
    id: int
    site_id: int
    organization_slug: str
    site_slug: str
    slug: str
    title: str
    description: str
    position: int
    status: str
    created_at: int
    updated_at: int


@dataclass(frozen=True)
class ContentItem:
    id: int
    collection_id: int
    site_id: int
    organization_slug: str
    site_slug: str
    title: str
    target: str
    position: int
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    tenant_sites.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS creator_collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                slug TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                position INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(site_id, slug),
                CHECK(status IN ('draft','published','archived')),
                FOREIGN KEY(site_id)
                    REFERENCES site_builder_sites(id) ON DELETE CASCADE
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS creator_collection_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_id INTEGER NOT NULL,
                site_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                target TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY(collection_id)
                    REFERENCES creator_collections(id) ON DELETE CASCADE,
                FOREIGN KEY(site_id)
                    REFERENCES site_builder_sites(id) ON DELETE CASCADE
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_creator_collections_site_status_position '
            'ON creator_collections(site_id, status, position, id)'
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_creator_collection_items_collection_position '
            'ON creator_collection_items(collection_id, position, id)'
        )
        conn.commit()


def _site(organization_slug: str, site_slug: str):
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        raise ValueError('Site not found.')
    return site


def _slug(value: str) -> str:
    clean = (value or '').strip().lower()
    if not clean or not _SLUG_RE.fullmatch(clean):
        raise ValueError(
            'Collection slug must contain lowercase letters/numbers separated by hyphens.'
        )
    return clean


def _text(value: str, *, field: str, limit: int, required: bool = False) -> str:
    clean = (value or '').strip()
    if required and not clean:
        raise ValueError(f'{field} is required.')
    if len(clean) > limit:
        raise ValueError(f'{field} must be {limit} characters or fewer.')
    return clean


def _position(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError('Position must be an integer.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Position must be an integer.') from exc
    if clean < 0:
        raise ValueError('Position cannot be negative.')
    return clean


def _status(value: str) -> str:
    clean = (value or '').strip().lower()
    if clean not in COLLECTION_STATUSES:
        raise ValueError(f'Unknown collection status: {clean}')
    return clean


def _target(value: str) -> str:
    clean = (value or '').strip()
    if not clean:
        raise ValueError('Content item target is required.')
    if clean.startswith('/'):
        if clean.startswith('//'):
            raise ValueError(
                'Internal content targets must be root-relative paths.'
            )
        return clean
    parsed = urlsplit(clean)
    if (
        parsed.scheme.lower() != 'https'
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(
            'External content targets must use credential-free HTTPS URLs.'
        )
    return clean


def create_collection(
    organization_slug: str,
    site_slug: str,
    *,
    slug: str,
    title: str,
    description: str = '',
    position: int = 0,
    status: str = 'draft',
) -> ContentCollection:
    site = _site(organization_slug, site_slug)
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')
    ensure_schema()
    now = tenant_auth.now()
    try:
        with tenant_auth.db() as conn:
            cursor = conn.execute(
                '''
                INSERT INTO creator_collections(
                    site_id,slug,title,description,position,status,
                    created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?)
                ''',
                (
                    site.id,
                    _slug(slug),
                    _text(title, field='Collection title', limit=200, required=True),
                    _text(description, field='Collection description', limit=4000),
                    _position(position),
                    _status(status),
                    now,
                    now,
                ),
            )
            conn.commit()
            row = _select_collection(conn, site.id, int(cursor.lastrowid))
    except sqlite3.IntegrityError as exc:
        raise ValueError(
            'A collection with that slug already exists for this site.'
        ) from exc
    return _collection_from_row(row)


def get_collection(
    organization_slug: str,
    site_slug: str,
    collection_id: int,
) -> ContentCollection | None:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        return None
    ensure_schema()
    with tenant_auth.db() as conn:
        row = _select_collection(conn, site.id, int(collection_id))
    return _collection_from_row(row) if row else None


def list_collections(
    organization_slug: str,
    site_slug: str,
    *,
    published_only: bool = False,
    include_archived: bool = False,
) -> list[ContentCollection]:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        return []
    ensure_schema()
    sql = '''
        SELECT c.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM creator_collections c
        JOIN site_builder_sites s ON s.id=c.site_id
        JOIN auth_organizations o ON o.id=s.organization_id
        WHERE c.site_id=?
    '''
    params: list[object] = [site.id]
    if published_only:
        sql += " AND c.status='published'"
    elif not include_archived:
        sql += " AND c.status!='archived'"
    sql += ' ORDER BY c.position, c.id'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_collection_from_row(row) for row in rows]


def update_collection(
    organization_slug: str,
    site_slug: str,
    collection_id: int,
    *,
    title: str | None = None,
    description: str | None = None,
    position: int | None = None,
    status: str | None = None,
) -> ContentCollection | None:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        return None
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')
    existing = get_collection(organization_slug, site_slug, collection_id)
    if existing is None:
        return None
    if existing.status == 'archived':
        raise ValueError('Archived collections cannot be updated.')

    assignments: list[str] = []
    params: list[object] = []
    if title is not None:
        assignments.append('title=?')
        params.append(_text(title, field='Collection title', limit=200, required=True))
    if description is not None:
        assignments.append('description=?')
        params.append(_text(description, field='Collection description', limit=4000))
    if position is not None:
        assignments.append('position=?')
        params.append(_position(position))
    if status is not None:
        assignments.append('status=?')
        params.append(_status(status))
    if not assignments:
        return existing

    assignments.append('updated_at=?')
    params.append(tenant_auth.now())
    params.extend([site.id, int(collection_id)])
    with tenant_auth.db() as conn:
        conn.execute(
            f'UPDATE creator_collections SET {", ".join(assignments)} '
            'WHERE site_id=? AND id=?',
            params,
        )
        conn.commit()
        row = _select_collection(conn, site.id, int(collection_id))
    return _collection_from_row(row)


def archive_collection(
    organization_slug: str,
    site_slug: str,
    collection_id: int,
) -> ContentCollection | None:
    existing = get_collection(organization_slug, site_slug, collection_id)
    if existing is None:
        return None
    if existing.status == 'archived':
        return existing
    return update_collection(
        organization_slug, site_slug, collection_id, status='archived'
    )


def create_item(
    organization_slug: str,
    site_slug: str,
    collection_id: int,
    *,
    title: str,
    target: str,
    position: int = 0,
) -> ContentItem:
    site = _site(organization_slug, site_slug)
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')
    collection = get_collection(organization_slug, site_slug, collection_id)
    if collection is None:
        raise ValueError('Collection not found for this site.')
    if collection.status == 'archived':
        raise ValueError('Archived collections cannot be updated.')

    ensure_schema()
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        cursor = conn.execute(
            '''
            INSERT INTO creator_collection_items(
                collection_id,site_id,title,target,position,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?)
            ''',
            (
                collection.id,
                site.id,
                _text(title, field='Content item title', limit=200, required=True),
                _target(target),
                _position(position),
                now,
                now,
            ),
        )
        conn.commit()
        row = _select_item(conn, site.id, collection.id, int(cursor.lastrowid))
    return _item_from_row(row)


def list_items(
    organization_slug: str,
    site_slug: str,
    collection_id: int,
) -> list[ContentItem]:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        return []
    collection = get_collection(organization_slug, site_slug, collection_id)
    if collection is None:
        return []
    ensure_schema()
    with tenant_auth.db() as conn:
        rows = conn.execute(
            '''
            SELECT i.*, o.slug AS organization_slug, s.slug AS site_slug
            FROM creator_collection_items i
            JOIN site_builder_sites s ON s.id=i.site_id
            JOIN auth_organizations o ON o.id=s.organization_id
            WHERE i.site_id=? AND i.collection_id=?
            ORDER BY i.position, i.id
            ''',
            (site.id, collection.id),
        ).fetchall()
    return [_item_from_row(row) for row in rows]


def update_item(
    organization_slug: str,
    site_slug: str,
    collection_id: int,
    item_id: int,
    *,
    title: str | None = None,
    target: str | None = None,
    position: int | None = None,
) -> ContentItem | None:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        return None
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')
    collection = get_collection(organization_slug, site_slug, collection_id)
    if collection is None:
        return None
    if collection.status == 'archived':
        raise ValueError('Archived collections cannot be updated.')

    ensure_schema()
    with tenant_auth.db() as conn:
        existing = _select_item(conn, site.id, collection.id, int(item_id))
        if existing is None:
            return None

    assignments: list[str] = []
    params: list[object] = []
    if title is not None:
        assignments.append('title=?')
        params.append(_text(title, field='Content item title', limit=200, required=True))
    if target is not None:
        assignments.append('target=?')
        params.append(_target(target))
    if position is not None:
        assignments.append('position=?')
        params.append(_position(position))
    if not assignments:
        return _item_from_row(existing)

    assignments.append('updated_at=?')
    params.append(tenant_auth.now())
    params.extend([site.id, collection.id, int(item_id)])
    with tenant_auth.db() as conn:
        conn.execute(
            f'UPDATE creator_collection_items SET {", ".join(assignments)} '
            'WHERE site_id=? AND collection_id=? AND id=?',
            params,
        )
        conn.commit()
        row = _select_item(conn, site.id, collection.id, int(item_id))
    return _item_from_row(row)


def delete_item(
    organization_slug: str,
    site_slug: str,
    collection_id: int,
    item_id: int,
) -> bool:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        return False
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')
    collection = get_collection(organization_slug, site_slug, collection_id)
    if collection is None:
        return False
    if collection.status == 'archived':
        raise ValueError('Archived collections cannot be updated.')
    ensure_schema()
    with tenant_auth.db() as conn:
        cur = conn.execute(
            'DELETE FROM creator_collection_items '
            'WHERE site_id=? AND collection_id=? AND id=?',
            (site.id, collection.id, int(item_id)),
        )
        conn.commit()
    return cur.rowcount > 0


def _select_collection(conn: sqlite3.Connection, site_id: int, collection_id: int):
    return conn.execute(
        '''
        SELECT c.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM creator_collections c
        JOIN site_builder_sites s ON s.id=c.site_id
        JOIN auth_organizations o ON o.id=s.organization_id
        WHERE c.site_id=? AND c.id=?
        LIMIT 1
        ''',
        (site_id, collection_id),
    ).fetchone()


def _select_item(
    conn: sqlite3.Connection,
    site_id: int,
    collection_id: int,
    item_id: int,
):
    return conn.execute(
        '''
        SELECT i.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM creator_collection_items i
        JOIN site_builder_sites s ON s.id=i.site_id
        JOIN auth_organizations o ON o.id=s.organization_id
        WHERE i.site_id=? AND i.collection_id=? AND i.id=?
        LIMIT 1
        ''',
        (site_id, collection_id, item_id),
    ).fetchone()


def _collection_from_row(row) -> ContentCollection:
    return ContentCollection(
        id=int(row['id']),
        site_id=int(row['site_id']),
        organization_slug=str(row['organization_slug']),
        site_slug=str(row['site_slug']),
        slug=str(row['slug']),
        title=str(row['title']),
        description=str(row['description']),
        position=int(row['position']),
        status=str(row['status']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )


def _item_from_row(row) -> ContentItem:
    return ContentItem(
        id=int(row['id']),
        collection_id=int(row['collection_id']),
        site_id=int(row['site_id']),
        organization_slug=str(row['organization_slug']),
        site_slug=str(row['site_slug']),
        title=str(row['title']),
        target=str(row['target']),
        position=int(row['position']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
