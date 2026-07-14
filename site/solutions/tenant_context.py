from __future__ import annotations

from dataclasses import dataclass
import json
from urllib.parse import urlsplit

import tenant_auth


@dataclass(frozen=True)
class Tenant:
    id: int
    slug: str
    name: str
    status: str
    domain: str


def normalize_host(value: str) -> str:
    raw = (value or '').strip().lower()
    if not raw:
        return ''
    if '://' not in raw:
        raw = f'//{raw}'
    parsed = urlsplit(raw)
    host = parsed.hostname or ''
    return host.rstrip('.')


def ensure_schema() -> None:
    with tenant_auth.db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS tenant_domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                domain TEXT NOT NULL UNIQUE COLLATE NOCASE,
                is_primary INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY(organization_id) REFERENCES auth_organizations(id)
                    ON DELETE CASCADE
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS tenant_settings (
                organization_id INTEGER NOT NULL,
                setting_key TEXT NOT NULL,
                setting_value TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY(organization_id, setting_key),
                FOREIGN KEY(organization_id) REFERENCES auth_organizations(id)
                    ON DELETE CASCADE
            )
        ''')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_tenant_domains_lookup '
            'ON tenant_domains(domain, is_active)'
        )
        _seed_primary_domain(conn)
        conn.commit()


def _seed_primary_domain(conn) -> None:
    domain = normalize_host(tenant_auth.PRIMARY_DOMAIN)
    if not domain:
        return
    organization = conn.execute(
        "SELECT id FROM auth_organizations WHERE slug = 'solutions'"
    ).fetchone()
    if not organization:
        return
    timestamp = tenant_auth.now()
    conn.execute(
        '''INSERT INTO tenant_domains(
               organization_id, domain, is_primary, is_active,
               created_at, updated_at
           ) VALUES (?, ?, 1, 1, ?, ?)
           ON CONFLICT(domain) DO UPDATE SET
               organization_id = excluded.organization_id,
               is_primary = 1,
               is_active = 1,
               updated_at = excluded.updated_at''',
        (organization['id'], domain, timestamp, timestamp),
    )


def get_tenant_by_slug(slug: str) -> Tenant | None:
    ensure_schema()
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''SELECT o.id, o.slug, o.name, o.status,
                      COALESCE(d.domain, '') AS domain
               FROM auth_organizations o
               LEFT JOIN tenant_domains d
                 ON d.organization_id = o.id
                AND d.is_primary = 1
                AND d.is_active = 1
               WHERE o.slug = ?
               ORDER BY d.id
               LIMIT 1''',
            ((slug or '').strip().lower(),),
        ).fetchone()
    return _tenant_from_row(row)


def resolve_tenant(host: str) -> Tenant | None:
    domain = normalize_host(host)
    if not domain:
        return None
    ensure_schema()
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''SELECT o.id, o.slug, o.name, o.status, d.domain
               FROM tenant_domains d
               JOIN auth_organizations o ON o.id = d.organization_id
               WHERE lower(d.domain) = lower(?)
                 AND d.is_active = 1
                 AND o.status = 'active'
               LIMIT 1''',
            (domain,),
        ).fetchone()
    return _tenant_from_row(row)


def register_domain(
    organization_slug: str,
    domain: str,
    *,
    primary: bool = False,
) -> bool:
    normalized = normalize_host(domain)
    if not normalized:
        return False
    ensure_schema()
    with tenant_auth.db() as conn:
        organization = conn.execute(
            'SELECT id FROM auth_organizations WHERE slug = ?',
            ((organization_slug or '').strip().lower(),),
        ).fetchone()
        if not organization:
            return False
        timestamp = tenant_auth.now()
        if primary:
            conn.execute(
                'UPDATE tenant_domains SET is_primary = 0, updated_at = ? '
                'WHERE organization_id = ?',
                (timestamp, organization['id']),
            )
        conn.execute(
            '''INSERT INTO tenant_domains(
                   organization_id, domain, is_primary, is_active,
                   created_at, updated_at
               ) VALUES (?, ?, ?, 1, ?, ?)
               ON CONFLICT(domain) DO UPDATE SET
                   organization_id = excluded.organization_id,
                   is_primary = excluded.is_primary,
                   is_active = 1,
                   updated_at = excluded.updated_at''',
            (
                organization['id'],
                normalized,
                1 if primary else 0,
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
    return True


def set_setting(organization_slug: str, key: str, value: object) -> bool:
    setting_key = (key or '').strip()
    if not setting_key:
        return False
    ensure_schema()
    with tenant_auth.db() as conn:
        organization = conn.execute(
            'SELECT id FROM auth_organizations WHERE slug = ?',
            ((organization_slug or '').strip().lower(),),
        ).fetchone()
        if not organization:
            return False
        conn.execute(
            '''INSERT INTO tenant_settings(
                   organization_id, setting_key, setting_value, updated_at
               ) VALUES (?, ?, ?, ?)
               ON CONFLICT(organization_id, setting_key) DO UPDATE SET
                   setting_value = excluded.setting_value,
                   updated_at = excluded.updated_at''',
            (
                organization['id'],
                setting_key,
                json.dumps(value, separators=(',', ':'), sort_keys=True),
                tenant_auth.now(),
            ),
        )
        conn.commit()
    return True


def get_settings(organization_slug: str) -> dict[str, object]:
    ensure_schema()
    with tenant_auth.db() as conn:
        rows = conn.execute(
            '''SELECT s.setting_key, s.setting_value
               FROM tenant_settings s
               JOIN auth_organizations o ON o.id = s.organization_id
               WHERE o.slug = ?
               ORDER BY s.setting_key''',
            ((organization_slug or '').strip().lower(),),
        ).fetchall()
    settings: dict[str, object] = {}
    for row in rows:
        try:
            settings[row['setting_key']] = json.loads(row['setting_value'])
        except (TypeError, json.JSONDecodeError):
            settings[row['setting_key']] = row['setting_value']
    return settings


def _tenant_from_row(row) -> Tenant | None:
    if not row:
        return None
    return Tenant(
        id=int(row['id']),
        slug=str(row['slug']),
        name=str(row['name']),
        status=str(row['status']),
        domain=str(row['domain'] or ''),
    )
