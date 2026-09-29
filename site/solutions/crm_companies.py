from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from urllib.parse import urlsplit

import crm_tenancy
import tenant_auth


COMPANY_STATUSES = ('prospect', 'customer', 'vendor', 'archived')


@dataclass(frozen=True)
class Company:
    id: int
    organization_id: int
    organization_slug: str
    name: str
    website: str
    industry: str
    status: str
    notes: str
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS crm_v2_companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                website TEXT NOT NULL DEFAULT '',
                industry TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'prospect',
                notes TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                CHECK(status IN ('prospect', 'customer', 'vendor', 'archived')),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_crm_v2_companies_org_status_name '
            'ON crm_v2_companies(organization_id, status, name COLLATE NOCASE, id)'
        )
        conn.commit()


def _clean_name(value: str) -> str:
    value = (value or '').strip()
    if not value:
        raise ValueError('Company name is required.')
    if len(value) > 200:
        raise ValueError('Company name must be 200 characters or fewer.')
    return value


def _clean_website(value: str) -> str:
    value = (value or '').strip()
    if not value:
        return ''
    parsed = urlsplit(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise ValueError('Company website must be an http/https URL.')
    return value


def _clean_status(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in COMPANY_STATUSES:
        raise ValueError(f'Unknown company status: {value}')
    return value


def _org_id(organization_slug: str) -> int:
    return crm_tenancy.organization_id(organization_slug)


def create_company(
    organization_slug: str,
    *,
    name: str,
    website: str = '',
    industry: str = '',
    status: str = 'prospect',
    notes: str = '',
) -> Company:
    organization_id = _org_id(organization_slug)
    clean_name = _clean_name(name)
    clean_website = _clean_website(website)
    clean_status = _clean_status(status)
    timestamp = tenant_auth.now()
    ensure_schema()
    with tenant_auth.db() as conn:
        cursor = conn.execute(
            '''
            INSERT INTO crm_v2_companies(
                organization_id, name, website, industry, status, notes,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                organization_id,
                clean_name,
                clean_website,
                (industry or '').strip(),
                clean_status,
                notes or '',
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
        row = _select(conn, organization_id, int(cursor.lastrowid))
    return _from_row(row)


def get_company(
    organization_slug: str,
    company_id: int,
) -> Company | None:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        row = _select(conn, organization_id, int(company_id))
    return _from_row(row) if row else None


def list_companies(
    organization_slug: str,
    *,
    query: str = '',
    status: str | None = None,
    include_archived: bool = False,
) -> list[Company]:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    sql = '''
        SELECT c.*, o.slug AS organization_slug
        FROM crm_v2_companies c
        JOIN auth_organizations o ON o.id = c.organization_id
        WHERE c.organization_id = ?
    '''
    params: list[object] = [organization_id]
    if status is not None:
        sql += ' AND c.status = ?'
        params.append(_clean_status(status))
    elif not include_archived:
        sql += " AND c.status != 'archived'"
    clean_query = (query or '').strip()
    if clean_query:
        sql += '''
            AND (
                c.name LIKE ? ESCAPE '\\'
                OR c.website LIKE ? ESCAPE '\\'
                OR c.industry LIKE ? ESCAPE '\\'
                OR c.notes LIKE ? ESCAPE '\\'
            )
        '''
        escaped = (
            clean_query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        )
        like = f'%{escaped}%'
        params.extend([like, like, like, like])
    sql += ' ORDER BY c.name COLLATE NOCASE, c.id'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_from_row(row) for row in rows]


def update_company(
    organization_slug: str,
    company_id: int,
    *,
    name: str | None = None,
    website: str | None = None,
    industry: str | None = None,
    status: str | None = None,
    notes: str | None = None,
) -> Company | None:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        existing = _select(conn, organization_id, int(company_id))
        if existing is None:
            return None
        if existing['status'] == 'archived':
            raise ValueError('Archived companies cannot be updated.')

        assignments: list[str] = []
        params: list[object] = []
        if name is not None:
            assignments.append('name = ?')
            params.append(_clean_name(name))
        if website is not None:
            assignments.append('website = ?')
            params.append(_clean_website(website))
        if industry is not None:
            assignments.append('industry = ?')
            params.append(industry.strip())
        if status is not None:
            assignments.append('status = ?')
            params.append(_clean_status(status))
        if notes is not None:
            assignments.append('notes = ?')
            params.append(notes)

        if not assignments:
            return _from_row(existing)

        assignments.append('updated_at = ?')
        params.append(tenant_auth.now())
        params.extend([organization_id, int(company_id)])
        conn.execute(
            f'''
            UPDATE crm_v2_companies
            SET {', '.join(assignments)}
            WHERE organization_id = ? AND id = ?
            ''',
            params,
        )
        conn.commit()
        row = _select(conn, organization_id, int(company_id))
    return _from_row(row)


def archive_company(
    organization_slug: str,
    company_id: int,
) -> Company | None:
    company = get_company(organization_slug, company_id)
    if company is None:
        return None
    if company.status == 'archived':
        return company
    return update_company(
        organization_slug,
        company_id,
        status='archived',
    )


def _select(conn: sqlite3.Connection, organization_id: int, company_id: int):
    return conn.execute(
        '''
        SELECT c.*, o.slug AS organization_slug
        FROM crm_v2_companies c
        JOIN auth_organizations o ON o.id = c.organization_id
        WHERE c.organization_id = ? AND c.id = ?
        LIMIT 1
        ''',
        (organization_id, company_id),
    ).fetchone()


def _from_row(row) -> Company:
    return Company(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        name=str(row['name']),
        website=str(row['website']),
        industry=str(row['industry']),
        status=str(row['status']),
        notes=str(row['notes']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
