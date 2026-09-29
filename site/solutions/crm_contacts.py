from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3

import crm_companies
import crm_tenancy
import tenant_auth


CONTACT_STATUSES = ('lead', 'prospect', 'customer', 'vendor', 'archived')
_EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


@dataclass(frozen=True)
class Contact:
    id: int
    organization_id: int
    organization_slug: str
    company_id: int | None
    company_name: str
    name: str
    email: str
    phone: str
    title: str
    status: str
    tags: str
    notes: str
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    crm_companies.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS crm_v2_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                company_id INTEGER,
                name TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'lead',
                tags TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                CHECK(status IN ('lead', 'prospect', 'customer', 'vendor', 'archived')),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(company_id)
                    REFERENCES crm_v2_companies(id) ON DELETE SET NULL
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_crm_v2_contacts_org_status_name '
            'ON crm_v2_contacts(organization_id, status, name COLLATE NOCASE, id)'
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_crm_v2_contacts_org_company '
            'ON crm_v2_contacts(organization_id, company_id, id)'
        )
        conn.commit()


def _clean_name(value: str) -> str:
    value = (value or '').strip()
    if not value:
        raise ValueError('Contact name is required.')
    if len(value) > 200:
        raise ValueError('Contact name must be 200 characters or fewer.')
    return value


def _clean_email(value: str) -> str:
    value = (value or '').strip().lower()
    if not value:
        return ''
    if len(value) > 320 or not _EMAIL_RE.fullmatch(value):
        raise ValueError('Contact email is invalid.')
    return value


def _clean_phone(value: str) -> str:
    value = (value or '').strip()
    if not value:
        return ''
    digits = ''.join(ch for ch in value if ch.isdigit())
    if len(digits) < 7 or len(digits) > 15:
        raise ValueError('Contact phone must contain 7 to 15 digits.')
    return ('+' if value.startswith('+') else '') + digits


def _clean_status(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in CONTACT_STATUSES:
        raise ValueError(f'Unknown contact status: {value}')
    return value


def _org_id(organization_slug: str) -> int:
    return crm_tenancy.organization_id(organization_slug)


def create_contact(
    organization_slug: str,
    *,
    name: str,
    email: str = '',
    phone: str = '',
    title: str = '',
    company_id: int | None = None,
    status: str = 'lead',
    tags: str = '',
    notes: str = '',
) -> Contact:
    organization_id = _org_id(organization_slug)
    clean_name = _clean_name(name)
    clean_email = _clean_email(email)
    clean_phone = _clean_phone(phone)
    clean_status = _clean_status(status)
    ensure_schema()
    timestamp = tenant_auth.now()
    with tenant_auth.db() as conn:
        crm_tenancy.ensure_same_organization(
            conn,
            organization_id=organization_id,
            table='crm_v2_companies',
            record_id=company_id,
        )
        cursor = conn.execute(
            '''
            INSERT INTO crm_v2_contacts(
                organization_id, company_id, name, email, phone, title,
                status, tags, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                organization_id,
                company_id,
                clean_name,
                clean_email,
                clean_phone,
                (title or '').strip(),
                clean_status,
                (tags or '').strip(),
                notes or '',
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
        row = _select(conn, organization_id, int(cursor.lastrowid))
    return _from_row(row)


def get_contact(
    organization_slug: str,
    contact_id: int,
) -> Contact | None:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        row = _select(conn, organization_id, int(contact_id))
    return _from_row(row) if row else None


def list_contacts(
    organization_slug: str,
    *,
    query: str = '',
    status: str | None = None,
    company_id: int | None = None,
    include_archived: bool = False,
) -> list[Contact]:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        if company_id is not None:
            crm_tenancy.ensure_same_organization(
                conn,
                organization_id=organization_id,
                table='crm_v2_companies',
                record_id=company_id,
            )
        sql = '''
            SELECT c.*, o.slug AS organization_slug,
                   COALESCE(co.name, '') AS company_name
            FROM crm_v2_contacts c
            JOIN auth_organizations o ON o.id = c.organization_id
            LEFT JOIN crm_v2_companies co
              ON co.id = c.company_id
             AND co.organization_id = c.organization_id
            WHERE c.organization_id = ?
        '''
        params: list[object] = [organization_id]
        if status is not None:
            sql += ' AND c.status = ?'
            params.append(_clean_status(status))
        elif not include_archived:
            sql += " AND c.status != 'archived'"
        if company_id is not None:
            sql += ' AND c.company_id = ?'
            params.append(company_id)
        clean_query = (query or '').strip()
        if clean_query:
            escaped = (
                clean_query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            )
            like = f'%{escaped}%'
            sql += '''
                AND (
                    c.name LIKE ? ESCAPE '\\'
                    OR c.email LIKE ? ESCAPE '\\'
                    OR c.phone LIKE ? ESCAPE '\\'
                    OR c.title LIKE ? ESCAPE '\\'
                    OR c.tags LIKE ? ESCAPE '\\'
                    OR c.notes LIKE ? ESCAPE '\\'
                    OR co.name LIKE ? ESCAPE '\\'
                )
            '''
            params.extend([like] * 7)
        sql += ' ORDER BY c.name COLLATE NOCASE, c.id'
        rows = conn.execute(sql, params).fetchall()
    return [_from_row(row) for row in rows]


def update_contact(
    organization_slug: str,
    contact_id: int,
    *,
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    title: str | None = None,
    company_id: int | None | object = ...,
    status: str | None = None,
    tags: str | None = None,
    notes: str | None = None,
) -> Contact | None:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        existing = _select(conn, organization_id, int(contact_id))
        if existing is None:
            return None
        if existing['status'] == 'archived':
            raise ValueError('Archived contacts cannot be updated.')

        assignments: list[str] = []
        params: list[object] = []
        if name is not None:
            assignments.append('name = ?')
            params.append(_clean_name(name))
        if email is not None:
            assignments.append('email = ?')
            params.append(_clean_email(email))
        if phone is not None:
            assignments.append('phone = ?')
            params.append(_clean_phone(phone))
        if title is not None:
            assignments.append('title = ?')
            params.append(title.strip())
        if company_id is not ...:
            crm_tenancy.ensure_same_organization(
                conn,
                organization_id=organization_id,
                table='crm_v2_companies',
                record_id=company_id,
            )
            assignments.append('company_id = ?')
            params.append(company_id)
        if status is not None:
            assignments.append('status = ?')
            params.append(_clean_status(status))
        if tags is not None:
            assignments.append('tags = ?')
            params.append(tags.strip())
        if notes is not None:
            assignments.append('notes = ?')
            params.append(notes)

        if not assignments:
            return _from_row(existing)

        assignments.append('updated_at = ?')
        params.append(tenant_auth.now())
        params.extend([organization_id, int(contact_id)])
        conn.execute(
            f'''
            UPDATE crm_v2_contacts
            SET {', '.join(assignments)}
            WHERE organization_id = ? AND id = ?
            ''',
            params,
        )
        conn.commit()
        row = _select(conn, organization_id, int(contact_id))
    return _from_row(row)


def archive_contact(
    organization_slug: str,
    contact_id: int,
) -> Contact | None:
    contact = get_contact(organization_slug, contact_id)
    if contact is None:
        return None
    if contact.status == 'archived':
        return contact
    return update_contact(
        organization_slug,
        contact_id,
        status='archived',
    )


def _select(conn: sqlite3.Connection, organization_id: int, contact_id: int):
    return conn.execute(
        '''
        SELECT c.*, o.slug AS organization_slug,
               COALESCE(co.name, '') AS company_name
        FROM crm_v2_contacts c
        JOIN auth_organizations o ON o.id = c.organization_id
        LEFT JOIN crm_v2_companies co
          ON co.id = c.company_id
         AND co.organization_id = c.organization_id
        WHERE c.organization_id = ? AND c.id = ?
        LIMIT 1
        ''',
        (organization_id, contact_id),
    ).fetchone()


def _from_row(row) -> Contact:
    return Contact(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        company_id=int(row['company_id']) if row['company_id'] is not None else None,
        company_name=str(row['company_name']),
        name=str(row['name']),
        email=str(row['email']),
        phone=str(row['phone']),
        title=str(row['title']),
        status=str(row['status']),
        tags=str(row['tags']),
        notes=str(row['notes']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
