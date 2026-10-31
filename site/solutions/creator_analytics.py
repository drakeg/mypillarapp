from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3

import creator_affiliates
import creator_collections
import creator_downloads
import creator_profiles
import creator_storefront
import tenant_auth
import tenant_sites


EVENT_TYPES = (
    'creator_page_view',
    'creator_link_click',
    'affiliate_click',
    'collection_open',
    'download_view',
    'download_interaction',
    'product_view',
    'product_interaction',
)
TARGET_TYPES = ('', 'creator_link', 'affiliate', 'collection', 'download', 'product')
_TARGET_EVENT_TYPES = {
    'creator_page_view': {''},
    'creator_link_click': {'creator_link'},
    'affiliate_click': {'affiliate'},
    'collection_open': {'collection'},
    'download_view': {'download'},
    'download_interaction': {'download'},
    'product_view': {'product'},
    'product_interaction': {'product'},
}


@dataclass(frozen=True)
class CreatorAnalyticsEvent:
    id: int
    site_id: int
    organization_slug: str
    site_slug: str
    event_type: str
    target_type: str
    target_id: int | None
    metadata: dict[str, str]
    created_at: int


def ensure_schema() -> None:
    creator_profiles.ensure_schema()
    creator_affiliates.ensure_schema()
    creator_collections.ensure_schema()
    creator_downloads.ensure_schema()
    creator_storefront.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS creator_analytics_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                target_type TEXT NOT NULL DEFAULT '',
                target_id INTEGER,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                CHECK(event_type IN (
                    'creator_page_view',
                    'creator_link_click',
                    'affiliate_click',
                    'collection_open',
                    'download_view',
                    'download_interaction',
                    'product_view',
                    'product_interaction'
                )),
                CHECK(target_type IN (
                    '',
                    'creator_link',
                    'affiliate',
                    'collection',
                    'download',
                    'product'
                )),
                FOREIGN KEY(site_id)
                    REFERENCES site_builder_sites(id) ON DELETE CASCADE
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_creator_analytics_site_time '
            'ON creator_analytics_events(site_id, created_at DESC, id DESC)'
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_creator_analytics_site_type_time '
            'ON creator_analytics_events(site_id, event_type, created_at DESC, id DESC)'
        )
        conn.commit()


def _site(organization_slug: str, site_slug: str):
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        raise ValueError('Site not found.')
    return site


def _event_type(value: str) -> str:
    clean = (value or '').strip().lower()
    if clean not in EVENT_TYPES:
        raise ValueError(f'Unknown creator analytics event type: {clean}')
    return clean


def _target_type(value: str) -> str:
    clean = (value or '').strip().lower()
    if clean not in TARGET_TYPES:
        raise ValueError(f'Unknown creator analytics target type: {clean}')
    return clean


def _target_id(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError('Creator analytics target id must be a positive integer.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            'Creator analytics target id must be a positive integer.'
        ) from exc
    if clean <= 0:
        raise ValueError('Creator analytics target id must be a positive integer.')
    return clean


def _metadata(value: dict[str, str] | None) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError('Creator analytics metadata must be an object.')
    if len(value) > 20:
        raise ValueError('Creator analytics metadata supports at most 20 keys.')

    clean: dict[str, str] = {}
    total = 0
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str) or not isinstance(raw_value, str):
            raise ValueError(
                'Creator analytics metadata keys and values must be strings.'
            )
        key = raw_key.strip()
        val = raw_value.strip()
        if not key or len(key) > 80:
            raise ValueError(
                'Creator analytics metadata keys must be 1-80 characters.'
            )
        if len(val) > 500:
            raise ValueError(
                'Creator analytics metadata values must be 500 characters or fewer.'
            )
        lowered = val.lower()
        if '<script' in lowered or 'javascript:' in lowered:
            raise ValueError(
                'Creator analytics metadata cannot contain executable script content.'
            )
        total += len(key) + len(val)
        if total > 4000:
            raise ValueError(
                'Creator analytics metadata must be 4000 characters or fewer.'
            )
        clean[key] = val
    return clean


def _validate_target(
    organization_slug: str,
    site_slug: str,
    site_id: int,
    event_type: str,
    target_type: str,
    target_id: int | None,
) -> None:
    allowed = _TARGET_EVENT_TYPES[event_type]
    if target_type not in allowed:
        raise ValueError(
            f'{event_type} does not support target type {target_type!r}.'
        )
    if not target_type:
        if target_id is not None:
            raise ValueError('Target id is not allowed for this event type.')
        return
    if target_id is None:
        raise ValueError('Target id is required for this event type.')

    if target_type == 'creator_link':
        record = creator_profiles.get_link(
            organization_slug, site_slug, target_id
        )
    elif target_type == 'affiliate':
        record = creator_affiliates.get_affiliate(
            organization_slug, site_slug, target_id
        )
    elif target_type == 'collection':
        record = creator_collections.get_collection(
            organization_slug, site_slug, target_id
        )
    elif target_type == 'download':
        record = creator_downloads.get_download(
            organization_slug, site_slug, target_id
        )
    else:
        record = creator_storefront.get_product(
            organization_slug, site_slug, target_id
        )

    if record is None or int(record.site_id) != int(site_id):
        raise ValueError(
            'Creator analytics target is unavailable for this site.'
        )


def record_event(
    organization_slug: str,
    site_slug: str,
    *,
    event_type: str,
    target_type: str = '',
    target_id: int | None = None,
    metadata: dict[str, str] | None = None,
) -> CreatorAnalyticsEvent:
    site = _site(organization_slug, site_slug)
    if site.status == 'archived':
        raise ValueError('Archived sites cannot accept analytics events.')

    clean_event = _event_type(event_type)
    clean_target_type = _target_type(target_type)
    clean_target_id = _target_id(target_id)
    clean_metadata = _metadata(metadata)
    _validate_target(
        organization_slug,
        site_slug,
        site.id,
        clean_event,
        clean_target_type,
        clean_target_id,
    )

    ensure_schema()
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        cur = conn.execute(
            '''
            INSERT INTO creator_analytics_events(
                site_id,event_type,target_type,target_id,metadata_json,created_at
            ) VALUES(?,?,?,?,?,?)
            ''',
            (
                site.id,
                clean_event,
                clean_target_type,
                clean_target_id,
                json.dumps(
                    clean_metadata,
                    sort_keys=True,
                    separators=(',', ':'),
                ),
                now,
            ),
        )
        conn.commit()
        row = _select(conn, site.id, int(cur.lastrowid))
    return _from_row(row)


def list_events(
    organization_slug: str,
    site_slug: str,
    *,
    event_type: str | None = None,
    limit: int = 100,
) -> list[CreatorAnalyticsEvent]:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None:
        return []
    if isinstance(limit, bool):
        raise ValueError('Analytics limit must be an integer between 1 and 500.')
    try:
        clean_limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            'Analytics limit must be an integer between 1 and 500.'
        ) from exc
    if clean_limit < 1 or clean_limit > 500:
        raise ValueError('Analytics limit must be an integer between 1 and 500.')

    ensure_schema()
    sql = '''
        SELECT e.*,o.slug AS organization_slug,s.slug AS site_slug
        FROM creator_analytics_events e
        JOIN site_builder_sites s ON s.id=e.site_id
        JOIN auth_organizations o ON o.id=s.organization_id
        WHERE e.site_id=?
    '''
    params: list[object] = [site.id]
    if event_type is not None:
        sql += ' AND e.event_type=?'
        params.append(_event_type(event_type))
    sql += ' ORDER BY e.created_at DESC,e.id DESC LIMIT ?'
    params.append(clean_limit)

    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_from_row(row) for row in rows]


def _select(conn: sqlite3.Connection, site_id: int, event_id: int):
    return conn.execute(
        '''
        SELECT e.*,o.slug AS organization_slug,s.slug AS site_slug
        FROM creator_analytics_events e
        JOIN site_builder_sites s ON s.id=e.site_id
        JOIN auth_organizations o ON o.id=s.organization_id
        WHERE e.site_id=? AND e.id=?
        LIMIT 1
        ''',
        (site_id, event_id),
    ).fetchone()


def _from_row(row) -> CreatorAnalyticsEvent:
    try:
        metadata = json.loads(row['metadata_json'])
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    safe_metadata = {
        str(key): str(value)
        for key, value in metadata.items()
        if isinstance(key, str) and isinstance(value, str)
    }
    return CreatorAnalyticsEvent(
        id=int(row['id']),
        site_id=int(row['site_id']),
        organization_slug=str(row['organization_slug']),
        site_slug=str(row['site_slug']),
        event_type=str(row['event_type']),
        target_type=str(row['target_type']),
        target_id=int(row['target_id']) if row['target_id'] is not None else None,
        metadata=safe_metadata,
        created_at=int(row['created_at']),
    )
