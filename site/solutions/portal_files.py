from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse
import sqlite3

import portal_projects
import portal_tickets
import tenant_auth


FILE_VISIBILITIES = ('customer', 'internal')
FILE_SOURCE_TYPES = ('external_url', 'storage_key')


@dataclass(frozen=True)
class PortalFile:
    id: int
    organization_id: int
    organization_slug: str
    customer_user_id: int
    customer_email: str
    project_id: int | None
    ticket_id: int | None
    name: str
    source_type: str
    source_ref: str
    mime_type: str
    visibility: str
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    portal_tickets.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS portal_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                customer_user_id INTEGER NOT NULL,
                customer_email TEXT NOT NULL COLLATE NOCASE,
                project_id INTEGER,
                ticket_id INTEGER,
                name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                mime_type TEXT NOT NULL DEFAULT '',
                visibility TEXT NOT NULL DEFAULT 'customer',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                CHECK(source_type IN ('external_url','storage_key')),
                CHECK(visibility IN ('customer','internal')),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(customer_user_id)
                    REFERENCES auth_users(id) ON DELETE RESTRICT,
                FOREIGN KEY(project_id)
                    REFERENCES portal_projects(id) ON DELETE SET NULL,
                FOREIGN KEY(ticket_id)
                    REFERENCES portal_tickets(id) ON DELETE SET NULL
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_portal_files_org_customer '
            'ON portal_files(organization_id, customer_user_id, updated_at DESC, id DESC)'
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_portal_files_org_project '
            'ON portal_files(organization_id, project_id, id)'
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_portal_files_org_ticket '
            'ON portal_files(organization_id, ticket_id, id)'
        )
        conn.commit()


def _org_id(organization_slug: str) -> int:
    return portal_projects._org_id(organization_slug)


def _clean_name(value: str) -> str:
    value = (value or '').strip()
    if not value:
        raise ValueError('File name is required.')
    if len(value) > 255:
        raise ValueError('File name must be 255 characters or fewer.')
    if '/' in value or '\\' in value:
        raise ValueError('File name cannot contain path separators.')
    return value


def _clean_mime(value: str) -> str:
    value = (value or '').strip().lower()
    if len(value) > 200:
        raise ValueError('MIME type must be 200 characters or fewer.')
    return value


def _clean_visibility(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in FILE_VISIBILITIES:
        raise ValueError(f'Unknown file visibility: {value}')
    return value


def _clean_source_type(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in FILE_SOURCE_TYPES:
        raise ValueError(f'Unknown file source type: {value}')
    return value


def _clean_source_ref(source_type: str, value: str) -> str:
    value = (value or '').strip()
    if not value:
        raise ValueError('File source reference is required.')
    if len(value) > 2048:
        raise ValueError('File source reference is too long.')
    if '\x00' in value:
        raise ValueError('File source reference is invalid.')

    if source_type == 'external_url':
        parsed = urlparse(value)
        if parsed.scheme not in {'https'} or not parsed.netloc:
            raise ValueError('External file URL must use HTTPS.')
        if parsed.username or parsed.password:
            raise ValueError('External file URL cannot contain embedded credentials.')
        return value

    # storage_key is opaque application metadata. It must not be an absolute
    # filesystem path, traversal path, or file:// URI.
    if value.startswith(('/', '\\')) or value.lower().startswith('file:'):
        raise ValueError('Storage key cannot be a local filesystem path.')
    parts = value.replace('\\', '/').split('/')
    if any(part in {'', '.', '..'} for part in parts):
        raise ValueError('Storage key contains an unsafe path segment.')
    return value


def _validate_customer(conn: sqlite3.Connection, organization_id: int,
                       customer_user_id: int) -> str:
    return portal_projects._validate_customer(
        conn, organization_id, customer_user_id
    )


def _validate_links(
    conn: sqlite3.Connection,
    organization_id: int,
    customer_user_id: int,
    project_id: int | None,
    ticket_id: int | None,
) -> None:
    project = None
    if project_id is not None:
        project = conn.execute(
            '''
            SELECT id, customer_user_id, status
            FROM portal_projects
            WHERE id=? AND organization_id=?
            ''',
            (int(project_id), organization_id),
        ).fetchone()
        if project is None:
            raise ValueError('File project is missing or belongs to another organization.')
        if int(project['customer_user_id']) != int(customer_user_id):
            raise ValueError('File project does not match the customer.')

    if ticket_id is not None:
        ticket = conn.execute(
            '''
            SELECT id, project_id, customer_user_id, status
            FROM portal_tickets
            WHERE id=? AND organization_id=?
            ''',
            (int(ticket_id), organization_id),
        ).fetchone()
        if ticket is None:
            raise ValueError('File ticket is missing or belongs to another organization.')
        if int(ticket['customer_user_id']) != int(customer_user_id):
            raise ValueError('File ticket does not match the customer.')
        if project_id is not None and ticket['project_id'] is not None:
            if int(ticket['project_id']) != int(project_id):
                raise ValueError('File project does not match the ticket project.')


def create_file(
    organization_slug: str,
    *,
    customer_user_id: int,
    name: str,
    source_type: str,
    source_ref: str,
    project_id: int | None = None,
    ticket_id: int | None = None,
    mime_type: str = '',
    visibility: str = 'customer',
) -> PortalFile:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    clean_source_type = _clean_source_type(source_type)
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        customer_email = _validate_customer(
            conn, organization_id, customer_user_id
        )
        _validate_links(
            conn, organization_id, customer_user_id, project_id, ticket_id
        )
        cur = conn.execute(
            '''
            INSERT INTO portal_files(
                organization_id, customer_user_id, customer_email,
                project_id, ticket_id, name, source_type, source_ref,
                mime_type, visibility, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                organization_id,
                int(customer_user_id),
                customer_email,
                project_id,
                ticket_id,
                _clean_name(name),
                clean_source_type,
                _clean_source_ref(clean_source_type, source_ref),
                _clean_mime(mime_type),
                _clean_visibility(visibility),
                now,
                now,
            ),
        )
        conn.commit()
        row = _select(conn, organization_id, int(cur.lastrowid))
    return _from_row(row)


def get_file(organization_slug: str, file_id: int) -> PortalFile | None:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        row = _select(conn, organization_id, int(file_id))
    return _from_row(row) if row else None


def list_files(
    organization_slug: str,
    *,
    customer_user_id: int | None = None,
    project_id: int | None = None,
    ticket_id: int | None = None,
    visibility: str | None = None,
) -> list[PortalFile]:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        if customer_user_id is not None:
            _validate_customer(conn, organization_id, customer_user_id)
        if project_id is not None or ticket_id is not None:
            # A link filter is valid only if it belongs to the tenant. When a
            # customer filter is present, it must also match that customer.
            expected_customer = customer_user_id
            if expected_customer is None:
                if project_id is not None:
                    row = conn.execute(
                        'SELECT customer_user_id FROM portal_projects WHERE id=? AND organization_id=?',
                        (int(project_id), organization_id),
                    ).fetchone()
                    if row is None:
                        raise ValueError('File project is missing or belongs to another organization.')
                    expected_customer = int(row['customer_user_id'])
                elif ticket_id is not None:
                    row = conn.execute(
                        'SELECT customer_user_id FROM portal_tickets WHERE id=? AND organization_id=?',
                        (int(ticket_id), organization_id),
                    ).fetchone()
                    if row is None:
                        raise ValueError('File ticket is missing or belongs to another organization.')
                    expected_customer = int(row['customer_user_id'])
            _validate_links(
                conn, organization_id, int(expected_customer),
                project_id, ticket_id
            )

        sql = '''
            SELECT f.*, o.slug AS organization_slug
            FROM portal_files f
            JOIN auth_organizations o ON o.id=f.organization_id
            WHERE f.organization_id=?
        '''
        params: list[object] = [organization_id]
        if customer_user_id is not None:
            sql += ' AND f.customer_user_id=?'
            params.append(int(customer_user_id))
        if project_id is not None:
            sql += ' AND f.project_id=?'
            params.append(int(project_id))
        if ticket_id is not None:
            sql += ' AND f.ticket_id=?'
            params.append(int(ticket_id))
        if visibility is not None:
            sql += ' AND f.visibility=?'
            params.append(_clean_visibility(visibility))
        sql += ' ORDER BY f.updated_at DESC, f.id DESC'
        rows = conn.execute(sql, params).fetchall()
    return [_from_row(row) for row in rows]


def update_visibility(
    organization_slug: str,
    file_id: int,
    visibility: str,
) -> PortalFile | None:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        existing = _select(conn, organization_id, int(file_id))
        if existing is None:
            return None
        conn.execute(
            '''
            UPDATE portal_files
            SET visibility=?, updated_at=?
            WHERE organization_id=? AND id=?
            ''',
            (
                _clean_visibility(visibility),
                tenant_auth.now(),
                organization_id,
                int(file_id),
            ),
        )
        conn.commit()
        row = _select(conn, organization_id, int(file_id))
    return _from_row(row)


def _select(conn: sqlite3.Connection, organization_id: int, file_id: int):
    return conn.execute(
        '''
        SELECT f.*, o.slug AS organization_slug
        FROM portal_files f
        JOIN auth_organizations o ON o.id=f.organization_id
        WHERE f.organization_id=? AND f.id=?
        LIMIT 1
        ''',
        (organization_id, file_id),
    ).fetchone()


def _from_row(row) -> PortalFile:
    return PortalFile(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        customer_user_id=int(row['customer_user_id']),
        customer_email=str(row['customer_email']),
        project_id=int(row['project_id']) if row['project_id'] is not None else None,
        ticket_id=int(row['ticket_id']) if row['ticket_id'] is not None else None,
        name=str(row['name']),
        source_type=str(row['source_type']),
        source_ref=str(row['source_ref']),
        mime_type=str(row['mime_type']),
        visibility=str(row['visibility']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
