from __future__ import annotations

import re
import sqlite3

import tenant_auth
import tenant_context

SLUG_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
VALID_STATUSES = {'active', 'inactive'}


def _slug(value: str) -> str:
    return (value or '').strip().lower()


def get_organization(slug: str) -> sqlite3.Row | None:
    tenant_context.ensure_schema()
    with tenant_auth.db() as conn:
        return conn.execute(
            '''SELECT o.id, o.slug, o.name, o.status, o.created_at, o.updated_at,
                      COALESCE(d.domain, '') AS primary_domain
               FROM auth_organizations o
               LEFT JOIN tenant_domains d
                 ON d.organization_id = o.id
                AND d.is_primary = 1
                AND d.is_active = 1
               WHERE o.slug = ?
               ORDER BY d.id
               LIMIT 1''',
            (_slug(slug),),
        ).fetchone()


def list_organizations(*, include_inactive: bool = True) -> list[sqlite3.Row]:
    tenant_context.ensure_schema()
    sql = '''SELECT o.id, o.slug, o.name, o.status, o.created_at, o.updated_at,
                    COALESCE(d.domain, '') AS primary_domain
             FROM auth_organizations o
             LEFT JOIN tenant_domains d
               ON d.organization_id = o.id
              AND d.is_primary = 1
              AND d.is_active = 1'''
    if not include_inactive:
        sql += " WHERE o.status = 'active'"
    sql += ' ORDER BY o.name, o.slug'
    with tenant_auth.db() as conn:
        return conn.execute(sql).fetchall()


def create_organization(*, slug: str, name: str, primary_domain: str = '') -> tuple[bool, str]:
    normalized_slug = _slug(slug)
    clean_name = (name or '').strip()
    domain = tenant_context.normalize_host(primary_domain)
    if not SLUG_RE.fullmatch(normalized_slug):
        return False, 'Slug must contain lowercase letters, numbers, and single hyphens.'
    if not clean_name:
        return False, 'Organization name is required.'
    if primary_domain and not domain:
        return False, 'Enter a valid domain.'

    tenant_context.ensure_schema()
    timestamp = tenant_auth.now()
    with tenant_auth.db() as conn:
        if conn.execute('SELECT 1 FROM auth_organizations WHERE slug = ?', (normalized_slug,)).fetchone():
            return False, 'An organization already uses that slug.'
        if domain and conn.execute(
            'SELECT 1 FROM tenant_domains WHERE lower(domain) = lower(?)', (domain,)
        ).fetchone():
            return False, 'A tenant already uses that domain.'
        cursor = conn.execute(
            '''INSERT INTO auth_organizations(created_at, updated_at, slug, name, status)
               VALUES (?, ?, ?, ?, 'active')''',
            (timestamp, timestamp, normalized_slug, clean_name),
        )
        if domain:
            conn.execute(
                '''INSERT INTO tenant_domains(
                       organization_id, domain, is_primary, is_active, created_at, updated_at
                   ) VALUES (?, ?, 1, 1, ?, ?)''',
                (cursor.lastrowid, domain, timestamp, timestamp),
            )
        conn.commit()
    return True, 'Organization created.'


def update_organization(slug: str, *, name: str | None = None, status: str | None = None) -> tuple[bool, str]:
    normalized_slug = _slug(slug)
    clean_name = None if name is None else name.strip()
    normalized_status = None if status is None else status.strip().lower()
    if clean_name == '':
        return False, 'Organization name is required.'
    if normalized_status is not None and normalized_status not in VALID_STATUSES:
        return False, 'Organization status must be active or inactive.'
    if clean_name is None and normalized_status is None:
        return False, 'No organization changes were supplied.'

    tenant_context.ensure_schema()
    with tenant_auth.db() as conn:
        organization = conn.execute(
            'SELECT id FROM auth_organizations WHERE slug = ?', (normalized_slug,)
        ).fetchone()
        if not organization:
            return False, 'Organization not found.'
        if clean_name is not None:
            conn.execute(
                'UPDATE auth_organizations SET name = ?, updated_at = ? WHERE id = ?',
                (clean_name, tenant_auth.now(), organization['id']),
            )
        if normalized_status is not None:
            conn.execute(
                'UPDATE auth_organizations SET status = ?, updated_at = ? WHERE id = ?',
                (normalized_status, tenant_auth.now(), organization['id']),
            )
        conn.commit()
    return True, 'Organization updated.'


def set_primary_domain(slug: str, domain: str) -> tuple[bool, str]:
    normalized_slug = _slug(slug)
    normalized_domain = tenant_context.normalize_host(domain)
    if not normalized_domain:
        return False, 'Enter a valid domain.'
    tenant_context.ensure_schema()
    timestamp = tenant_auth.now()
    with tenant_auth.db() as conn:
        organization = conn.execute(
            'SELECT id FROM auth_organizations WHERE slug = ?', (normalized_slug,)
        ).fetchone()
        if not organization:
            return False, 'Organization not found.'
        conflict = conn.execute(
            'SELECT organization_id FROM tenant_domains WHERE lower(domain) = lower(?)',
            (normalized_domain,),
        ).fetchone()
        if conflict and int(conflict['organization_id']) != int(organization['id']):
            return False, 'A tenant already uses that domain.'
        conn.execute(
            'UPDATE tenant_domains SET is_primary = 0, updated_at = ? WHERE organization_id = ?',
            (timestamp, organization['id']),
        )
        conn.execute(
            '''INSERT INTO tenant_domains(
                   organization_id, domain, is_primary, is_active, created_at, updated_at
               ) VALUES (?, ?, 1, 1, ?, ?)
               ON CONFLICT(domain) DO UPDATE SET
                   is_primary = 1, is_active = 1, updated_at = excluded.updated_at''',
            (organization['id'], normalized_domain, timestamp, timestamp),
        )
        conn.commit()
    return True, 'Primary domain updated.'
