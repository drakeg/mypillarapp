from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import tenant_auth
import tenant_sites


@dataclass(frozen=True)
class NavigationItem:
    id: int
    site_id: int
    organization_slug: str
    site_slug: str
    label: str
    target: str
    position: int
    is_visible: bool
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    tenant_sites.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS site_builder_navigation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                target TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                is_visible INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY(site_id)
                    REFERENCES site_builder_sites(id) ON DELETE CASCADE
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_site_builder_navigation_site_position '
            'ON site_builder_navigation(site_id, position, id)'
        )
        conn.commit()


def _normalize_label(value: str) -> str:
    return (value or '').strip()


def _normalize_target(value: str) -> str:
    return (value or '').strip()


def _valid_target(value: str) -> bool:
    if not value:
        return False
    if value.startswith('/'):
        return not value.startswith('//')
    parsed = urlsplit(value)
    return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)


def _site(organization_slug: str, site_slug: str):
    return tenant_sites.get_site(organization_slug, site_slug)


def create_item(
    organization_slug: str,
    site_slug: str,
    *,
    label: str,
    target: str,
    position: int = 0,
    is_visible: bool = True,
) -> NavigationItem:
    site = _site(organization_slug, site_slug)
    if not site:
        raise ValueError('Site not found.')
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')

    clean_label = _normalize_label(label)
    clean_target = _normalize_target(target)
    if not clean_label:
        raise ValueError('Navigation label is required.')
    if not _valid_target(clean_target):
        raise ValueError(
            'Navigation target must be a root-relative path or an http/https URL.'
        )
    try:
        clean_position = int(position)
    except (TypeError, ValueError) as exc:
        raise ValueError('Navigation position must be an integer.') from exc
    if clean_position < 0:
        raise ValueError('Navigation position cannot be negative.')

    ensure_schema()
    timestamp = tenant_auth.now()
    with tenant_auth.db() as conn:
        cursor = conn.execute(
            '''
            INSERT INTO site_builder_navigation(
                site_id, label, target, position, is_visible,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                site.id,
                clean_label,
                clean_target,
                clean_position,
                1 if is_visible else 0,
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
        row = _select_item(conn, site.id, int(cursor.lastrowid))
    return _item_from_row(row)


def list_items(
    organization_slug: str,
    site_slug: str,
    *,
    visible_only: bool = False,
) -> list[NavigationItem]:
    site = _site(organization_slug, site_slug)
    if not site:
        return []
    ensure_schema()
    sql = '''
        SELECT n.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM site_builder_navigation n
        JOIN site_builder_sites s ON s.id = n.site_id
        JOIN auth_organizations o ON o.id = s.organization_id
        WHERE n.site_id = ?
    '''
    params: list[object] = [site.id]
    if visible_only:
        sql += ' AND n.is_visible = 1'
    sql += ' ORDER BY n.position, n.id'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_item_from_row(row) for row in rows]


def get_item(
    organization_slug: str,
    site_slug: str,
    item_id: int,
) -> NavigationItem | None:
    site = _site(organization_slug, site_slug)
    if not site:
        return None
    ensure_schema()
    with tenant_auth.db() as conn:
        row = _select_item(conn, site.id, item_id)
    return _item_from_row(row) if row else None


def update_item(
    organization_slug: str,
    site_slug: str,
    item_id: int,
    *,
    label: str | None = None,
    target: str | None = None,
    position: int | None = None,
    is_visible: bool | None = None,
) -> NavigationItem | None:
    site = _site(organization_slug, site_slug)
    if not site:
        return None
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')

    assignments: list[str] = []
    params: list[object] = []

    if label is not None:
        clean_label = _normalize_label(label)
        if not clean_label:
            raise ValueError('Navigation label is required.')
        assignments.append('label = ?')
        params.append(clean_label)

    if target is not None:
        clean_target = _normalize_target(target)
        if not _valid_target(clean_target):
            raise ValueError(
                'Navigation target must be a root-relative path or an http/https URL.'
            )
        assignments.append('target = ?')
        params.append(clean_target)

    if position is not None:
        try:
            clean_position = int(position)
        except (TypeError, ValueError) as exc:
            raise ValueError('Navigation position must be an integer.') from exc
        if clean_position < 0:
            raise ValueError('Navigation position cannot be negative.')
        assignments.append('position = ?')
        params.append(clean_position)

    if is_visible is not None:
        assignments.append('is_visible = ?')
        params.append(1 if is_visible else 0)

    if not assignments:
        return get_item(organization_slug, site_slug, item_id)

    assignments.append('updated_at = ?')
    params.append(tenant_auth.now())
    params.extend([site.id, int(item_id)])

    ensure_schema()
    with tenant_auth.db() as conn:
        cursor = conn.execute(
            f'''
            UPDATE site_builder_navigation
            SET {', '.join(assignments)}
            WHERE site_id = ? AND id = ?
            ''',
            params,
        )
        conn.commit()
        if cursor.rowcount == 0:
            return None
        row = _select_item(conn, site.id, item_id)
    return _item_from_row(row)


def delete_item(
    organization_slug: str,
    site_slug: str,
    item_id: int,
) -> bool:
    site = _site(organization_slug, site_slug)
    if not site:
        return False
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')

    ensure_schema()
    with tenant_auth.db() as conn:
        cursor = conn.execute(
            'DELETE FROM site_builder_navigation WHERE site_id = ? AND id = ?',
            (site.id, int(item_id)),
        )
        conn.commit()
    return cursor.rowcount > 0


def _select_item(conn, site_id: int, item_id: int):
    return conn.execute(
        '''
        SELECT n.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM site_builder_navigation n
        JOIN site_builder_sites s ON s.id = n.site_id
        JOIN auth_organizations o ON o.id = s.organization_id
        WHERE n.site_id = ? AND n.id = ?
        LIMIT 1
        ''',
        (site_id, int(item_id)),
    ).fetchone()


def _item_from_row(row) -> NavigationItem:
    return NavigationItem(
        id=int(row['id']),
        site_id=int(row['site_id']),
        organization_slug=str(row['organization_slug']),
        site_slug=str(row['site_slug']),
        label=str(row['label']),
        target=str(row['target']),
        position=int(row['position']),
        is_visible=bool(row['is_visible']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
