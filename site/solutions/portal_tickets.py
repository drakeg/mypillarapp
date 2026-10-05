from __future__ import annotations

from dataclasses import dataclass
import sqlite3

import portal_projects
import tenant_auth


TICKET_STATUSES = ('open', 'in_progress', 'waiting_on_customer', 'resolved', 'closed', 'archived')
TICKET_PRIORITIES = ('low', 'normal', 'high', 'urgent')
TICKET_VISIBILITIES = ('customer', 'internal')


@dataclass(frozen=True)
class Ticket:
    id: int
    organization_id: int
    organization_slug: str
    project_id: int | None
    customer_user_id: int
    customer_email: str
    subject: str
    description: str
    status: str
    priority: str
    visibility: str
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    portal_projects.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS portal_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                project_id INTEGER,
                customer_user_id INTEGER NOT NULL,
                customer_email TEXT NOT NULL COLLATE NOCASE,
                subject TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                priority TEXT NOT NULL DEFAULT 'normal',
                visibility TEXT NOT NULL DEFAULT 'customer',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                CHECK(status IN (
                    'open','in_progress','waiting_on_customer',
                    'resolved','closed','archived'
                )),
                CHECK(priority IN ('low','normal','high','urgent')),
                CHECK(visibility IN ('customer','internal')),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(project_id)
                    REFERENCES portal_projects(id) ON DELETE SET NULL,
                FOREIGN KEY(customer_user_id)
                    REFERENCES auth_users(id) ON DELETE RESTRICT
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_portal_tickets_org_status '
            'ON portal_tickets(organization_id, status, updated_at DESC, id DESC)'
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_portal_tickets_org_customer '
            'ON portal_tickets(organization_id, customer_user_id, updated_at DESC, id DESC)'
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_portal_tickets_org_project '
            'ON portal_tickets(organization_id, project_id, updated_at DESC, id DESC)'
        )
        conn.commit()


def _org_id(organization_slug: str) -> int:
    return portal_projects._org_id(organization_slug)


def _clean_subject(value: str) -> str:
    value = (value or '').strip()
    if not value:
        raise ValueError('Ticket subject is required.')
    if len(value) > 200:
        raise ValueError('Ticket subject must be 200 characters or fewer.')
    return value


def _clean_description(value: str) -> str:
    value = (value or '').strip()
    if len(value) > 10000:
        raise ValueError('Ticket description must be 10000 characters or fewer.')
    return value


def _clean_status(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in TICKET_STATUSES:
        raise ValueError(f'Unknown ticket status: {value}')
    return value


def _clean_priority(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in TICKET_PRIORITIES:
        raise ValueError(f'Unknown ticket priority: {value}')
    return value


def _clean_visibility(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in TICKET_VISIBILITIES:
        raise ValueError(f'Unknown ticket visibility: {value}')
    return value


def _validate_customer(conn: sqlite3.Connection, organization_id: int, customer_user_id: int) -> str:
    return portal_projects._validate_customer(conn, organization_id, customer_user_id)


def _validate_project(
    conn: sqlite3.Connection,
    organization_id: int,
    project_id: int | None,
    customer_user_id: int,
) -> None:
    if project_id is None:
        return
    if isinstance(project_id, bool):
        raise ValueError('Ticket project is invalid.')
    try:
        project_id = int(project_id)
    except (TypeError, ValueError) as exc:
        raise ValueError('Ticket project is invalid.') from exc
    row = conn.execute(
        '''
        SELECT customer_user_id, status
        FROM portal_projects
        WHERE id=? AND organization_id=?
        ''',
        (project_id, organization_id),
    ).fetchone()
    if row is None:
        raise ValueError('Ticket project is missing or belongs to another organization.')
    if int(row['customer_user_id']) != int(customer_user_id):
        raise ValueError('Ticket customer does not match the project customer.')
    if row['status'] == 'archived':
        raise ValueError('Archived projects cannot accept tickets.')


def create_ticket(
    organization_slug: str,
    *,
    customer_user_id: int,
    subject: str,
    description: str = '',
    project_id: int | None = None,
    status: str = 'open',
    priority: str = 'normal',
    visibility: str = 'customer',
) -> Ticket:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        customer_email = _validate_customer(conn, organization_id, customer_user_id)
        _validate_project(conn, organization_id, project_id, customer_user_id)
        cur = conn.execute(
            '''
            INSERT INTO portal_tickets(
                organization_id, project_id, customer_user_id, customer_email,
                subject, description, status, priority, visibility,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                organization_id,
                project_id,
                int(customer_user_id),
                customer_email,
                _clean_subject(subject),
                _clean_description(description),
                _clean_status(status),
                _clean_priority(priority),
                _clean_visibility(visibility),
                now,
                now,
            ),
        )
        conn.commit()
        row = _select(conn, organization_id, int(cur.lastrowid))
    return _from_row(row)


def get_ticket(organization_slug: str, ticket_id: int) -> Ticket | None:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        row = _select(conn, organization_id, int(ticket_id))
    return _from_row(row) if row else None


def list_tickets(
    organization_slug: str,
    *,
    customer_user_id: int | None = None,
    project_id: int | None = None,
    status: str | None = None,
    priority: str | None = None,
    visibility: str | None = None,
    include_archived: bool = False,
) -> list[Ticket]:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        if customer_user_id is not None:
            _validate_customer(conn, organization_id, customer_user_id)
        if project_id is not None:
            project = conn.execute(
                'SELECT customer_user_id FROM portal_projects WHERE id=? AND organization_id=?',
                (int(project_id), organization_id),
            ).fetchone()
            if project is None:
                raise ValueError('Ticket project is missing or belongs to another organization.')
            if customer_user_id is not None and int(project['customer_user_id']) != int(customer_user_id):
                raise ValueError('Ticket project does not belong to the requested customer.')

        sql = '''
            SELECT t.*, o.slug AS organization_slug
            FROM portal_tickets t
            JOIN auth_organizations o ON o.id=t.organization_id
            WHERE t.organization_id=?
        '''
        params: list[object] = [organization_id]
        if customer_user_id is not None:
            sql += ' AND t.customer_user_id=?'
            params.append(int(customer_user_id))
        if project_id is not None:
            sql += ' AND t.project_id=?'
            params.append(int(project_id))
        if status is not None:
            sql += ' AND t.status=?'
            params.append(_clean_status(status))
        elif not include_archived:
            sql += " AND t.status!='archived'"
        if priority is not None:
            sql += ' AND t.priority=?'
            params.append(_clean_priority(priority))
        if visibility is not None:
            sql += ' AND t.visibility=?'
            params.append(_clean_visibility(visibility))
        sql += ' ORDER BY t.updated_at DESC, t.id DESC'
        rows = conn.execute(sql, params).fetchall()
    return [_from_row(row) for row in rows]


def update_ticket(
    organization_slug: str,
    ticket_id: int,
    *,
    subject: str | None = None,
    description: str | None = None,
    customer_user_id: int | None = None,
    project_id: int | None | object = ...,
    status: str | None = None,
    priority: str | None = None,
    visibility: str | None = None,
) -> Ticket | None:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        existing = _select(conn, organization_id, int(ticket_id))
        if existing is None:
            return None
        if existing['status'] == 'archived':
            raise ValueError('Archived tickets cannot be updated.')

        next_customer_id = (
            int(existing['customer_user_id'])
            if customer_user_id is None
            else int(customer_user_id)
        )
        next_customer_email = _validate_customer(
            conn, organization_id, next_customer_id
        )
        next_project = existing['project_id'] if project_id is ... else project_id
        _validate_project(
            conn, organization_id, next_project, next_customer_id
        )

        assignments: list[str] = []
        params: list[object] = []
        if subject is not None:
            assignments.append('subject=?')
            params.append(_clean_subject(subject))
        if description is not None:
            assignments.append('description=?')
            params.append(_clean_description(description))
        if customer_user_id is not None:
            assignments.extend(['customer_user_id=?', 'customer_email=?'])
            params.extend([next_customer_id, next_customer_email])
        if project_id is not ...:
            assignments.append('project_id=?')
            params.append(project_id)
        if status is not None:
            assignments.append('status=?')
            params.append(_clean_status(status))
        if priority is not None:
            assignments.append('priority=?')
            params.append(_clean_priority(priority))
        if visibility is not None:
            assignments.append('visibility=?')
            params.append(_clean_visibility(visibility))

        if not assignments:
            return _from_row(existing)

        assignments.append('updated_at=?')
        params.append(tenant_auth.now())
        params.extend([organization_id, int(ticket_id)])
        conn.execute(
            f'''
            UPDATE portal_tickets
            SET {', '.join(assignments)}
            WHERE organization_id=? AND id=?
            ''',
            params,
        )
        conn.commit()
        row = _select(conn, organization_id, int(ticket_id))
    return _from_row(row)


def archive_ticket(
    organization_slug: str,
    ticket_id: int,
) -> Ticket | None:
    ticket = get_ticket(organization_slug, ticket_id)
    if ticket is None:
        return None
    if ticket.status == 'archived':
        return ticket
    return update_ticket(
        organization_slug,
        ticket_id,
        status='archived',
    )


def _select(conn: sqlite3.Connection, organization_id: int, ticket_id: int):
    return conn.execute(
        '''
        SELECT t.*, o.slug AS organization_slug
        FROM portal_tickets t
        JOIN auth_organizations o ON o.id=t.organization_id
        WHERE t.organization_id=? AND t.id=?
        LIMIT 1
        ''',
        (organization_id, ticket_id),
    ).fetchone()


def _from_row(row) -> Ticket:
    return Ticket(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        project_id=int(row['project_id']) if row['project_id'] is not None else None,
        customer_user_id=int(row['customer_user_id']),
        customer_email=str(row['customer_email']),
        subject=str(row['subject']),
        description=str(row['description']),
        status=str(row['status']),
        priority=str(row['priority']),
        visibility=str(row['visibility']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
