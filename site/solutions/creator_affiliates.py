from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from urllib.parse import urlsplit

import tenant_auth
import tenant_sites


AFFILIATE_STATUSES = ('draft', 'published', 'archived')


@dataclass(frozen=True)
class AffiliateLink:
    id: int
    site_id: int
    organization_slug: str
    site_slug: str
    label: str
    destination_url: str
    network: str
    program: str
    disclosure_text: str
    tracking_code: str
    position: int
    status: str
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    tenant_sites.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS creator_affiliate_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                destination_url TEXT NOT NULL,
                network TEXT NOT NULL DEFAULT '',
                program TEXT NOT NULL DEFAULT '',
                disclosure_text TEXT NOT NULL,
                tracking_code TEXT NOT NULL DEFAULT '',
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
            'CREATE INDEX IF NOT EXISTS '
            'idx_creator_affiliate_links_site_status_position '
            'ON creator_affiliate_links(site_id, status, position, id)'
        )
        conn.commit()


def _site(organization_slug: str, site_slug: str):
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        raise ValueError('Site not found.')
    return site


def _text(
    value: str,
    *,
    field: str,
    limit: int,
    required: bool = False,
) -> str:
    clean = (value or '').strip()
    if required and not clean:
        raise ValueError(f'{field} is required.')
    if len(clean) > limit:
        raise ValueError(f'{field} must be {limit} characters or fewer.')
    if '<script' in clean.lower() or 'javascript:' in clean.lower():
        raise ValueError(f'{field} cannot contain executable script content.')
    return clean


def _destination(value: str) -> str:
    clean = (value or '').strip()
    parsed = urlsplit(clean)
    if (
        parsed.scheme.lower() != 'https'
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(
            'Affiliate destination must use a credential-free HTTPS URL.'
        )
    return clean


def _position(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError('Affiliate position must be an integer.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Affiliate position must be an integer.') from exc
    if clean < 0:
        raise ValueError('Affiliate position cannot be negative.')
    return clean


def _status(value: str) -> str:
    clean = (value or '').strip().lower()
    if clean not in AFFILIATE_STATUSES:
        raise ValueError(f'Unknown affiliate status: {clean}')
    return clean


def create_affiliate(
    organization_slug: str,
    site_slug: str,
    *,
    label: str,
    destination_url: str,
    disclosure_text: str,
    network: str = '',
    program: str = '',
    tracking_code: str = '',
    position: int = 0,
    status: str = 'draft',
) -> AffiliateLink:
    site = _site(organization_slug, site_slug)
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')

    ensure_schema()
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        cursor = conn.execute(
            '''
            INSERT INTO creator_affiliate_links(
                site_id, label, destination_url, network, program,
                disclosure_text, tracking_code, position, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                site.id,
                _text(label, field='Affiliate label', limit=160, required=True),
                _destination(destination_url),
                _text(network, field='Affiliate network', limit=160),
                _text(program, field='Affiliate program', limit=160),
                _text(
                    disclosure_text,
                    field='Affiliate disclosure',
                    limit=1000,
                    required=True,
                ),
                _text(tracking_code, field='Tracking code', limit=500),
                _position(position),
                _status(status),
                now,
                now,
            ),
        )
        conn.commit()
        row = _select(conn, site.id, int(cursor.lastrowid))
    return _from_row(row)


def get_affiliate(
    organization_slug: str,
    site_slug: str,
    affiliate_id: int,
) -> AffiliateLink | None:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        return None
    ensure_schema()
    with tenant_auth.db() as conn:
        row = _select(conn, site.id, int(affiliate_id))
    return _from_row(row) if row else None


def list_affiliates(
    organization_slug: str,
    site_slug: str,
    *,
    published_only: bool = False,
    include_archived: bool = False,
) -> list[AffiliateLink]:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        return []
    ensure_schema()
    sql = '''
        SELECT a.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM creator_affiliate_links a
        JOIN site_builder_sites s ON s.id=a.site_id
        JOIN auth_organizations o ON o.id=s.organization_id
        WHERE a.site_id=?
    '''
    params: list[object] = [site.id]
    if published_only:
        sql += " AND a.status='published'"
    elif not include_archived:
        sql += " AND a.status!='archived'"
    sql += ' ORDER BY a.position, a.id'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_from_row(row) for row in rows]


def update_affiliate(
    organization_slug: str,
    site_slug: str,
    affiliate_id: int,
    *,
    label: str | None = None,
    destination_url: str | None = None,
    disclosure_text: str | None = None,
    network: str | None = None,
    program: str | None = None,
    tracking_code: str | None = None,
    position: int | None = None,
    status: str | None = None,
) -> AffiliateLink | None:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        return None
    if site.status == 'archived':
        raise ValueError('Archived sites cannot be updated.')

    existing = get_affiliate(
        organization_slug, site_slug, affiliate_id
    )
    if existing is None:
        return None
    if existing.status == 'archived':
        raise ValueError('Archived affiliate links cannot be updated.')

    assignments: list[str] = []
    params: list[object] = []

    if label is not None:
        assignments.append('label=?')
        params.append(
            _text(label, field='Affiliate label', limit=160, required=True)
        )
    if destination_url is not None:
        assignments.append('destination_url=?')
        params.append(_destination(destination_url))
    if disclosure_text is not None:
        assignments.append('disclosure_text=?')
        params.append(
            _text(
                disclosure_text,
                field='Affiliate disclosure',
                limit=1000,
                required=True,
            )
        )
    if network is not None:
        assignments.append('network=?')
        params.append(_text(network, field='Affiliate network', limit=160))
    if program is not None:
        assignments.append('program=?')
        params.append(_text(program, field='Affiliate program', limit=160))
    if tracking_code is not None:
        assignments.append('tracking_code=?')
        params.append(_text(tracking_code, field='Tracking code', limit=500))
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
    params.extend([site.id, int(affiliate_id)])
    with tenant_auth.db() as conn:
        conn.execute(
            f'''
            UPDATE creator_affiliate_links
            SET {', '.join(assignments)}
            WHERE site_id=? AND id=?
            ''',
            params,
        )
        conn.commit()
        row = _select(conn, site.id, int(affiliate_id))
    return _from_row(row)


def archive_affiliate(
    organization_slug: str,
    site_slug: str,
    affiliate_id: int,
) -> AffiliateLink | None:
    existing = get_affiliate(
        organization_slug, site_slug, affiliate_id
    )
    if existing is None:
        return None
    if existing.status == 'archived':
        return existing
    return update_affiliate(
        organization_slug,
        site_slug,
        affiliate_id,
        status='archived',
    )


def _select(conn: sqlite3.Connection, site_id: int, affiliate_id: int):
    return conn.execute(
        '''
        SELECT a.*, o.slug AS organization_slug, s.slug AS site_slug
        FROM creator_affiliate_links a
        JOIN site_builder_sites s ON s.id=a.site_id
        JOIN auth_organizations o ON o.id=s.organization_id
        WHERE a.site_id=? AND a.id=?
        LIMIT 1
        ''',
        (site_id, affiliate_id),
    ).fetchone()


def _from_row(row) -> AffiliateLink:
    return AffiliateLink(
        id=int(row['id']),
        site_id=int(row['site_id']),
        organization_slug=str(row['organization_slug']),
        site_slug=str(row['site_slug']),
        label=str(row['label']),
        destination_url=str(row['destination_url']),
        network=str(row['network']),
        program=str(row['program']),
        disclosure_text=str(row['disclosure_text']),
        tracking_code=str(row['tracking_code']),
        position=int(row['position']),
        status=str(row['status']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
