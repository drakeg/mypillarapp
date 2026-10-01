from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import sqlite3

import crm_opportunities
import crm_tenancy
import tenant_auth


TASK_STATUSES = ('open', 'in_progress', 'done', 'canceled', 'archived')
TASK_PRIORITIES = ('low', 'normal', 'high', 'urgent')


@dataclass(frozen=True)
class CrmTask:
    id: int
    organization_id: int
    organization_slug: str
    company_id: int | None
    company_name: str
    contact_id: int | None
    contact_name: str
    opportunity_id: int | None
    opportunity_title: str
    title: str
    description: str
    status: str
    priority: str
    due_date: str
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    crm_opportunities.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS crm_v2_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                company_id INTEGER,
                contact_id INTEGER,
                opportunity_id INTEGER,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                priority TEXT NOT NULL DEFAULT 'normal',
                due_date TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                CHECK(status IN ('open','in_progress','done','canceled','archived')),
                CHECK(priority IN ('low','normal','high','urgent')),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(company_id)
                    REFERENCES crm_v2_companies(id) ON DELETE SET NULL,
                FOREIGN KEY(contact_id)
                    REFERENCES crm_v2_contacts(id) ON DELETE SET NULL,
                FOREIGN KEY(opportunity_id)
                    REFERENCES crm_v2_opportunities(id) ON DELETE SET NULL
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_crm_v2_tasks_org_status_due '
            'ON crm_v2_tasks(organization_id, status, due_date, id)'
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_crm_v2_tasks_org_priority '
            'ON crm_v2_tasks(organization_id, priority, id)'
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_crm_v2_tasks_org_relationships '
            'ON crm_v2_tasks(organization_id, company_id, contact_id, opportunity_id)'
        )
        conn.commit()


def _org_id(organization_slug: str) -> int:
    return crm_tenancy.organization_id(organization_slug)


def _clean_title(value: str) -> str:
    value = (value or '').strip()
    if not value:
        raise ValueError('CRM task title is required.')
    if len(value) > 200:
        raise ValueError('CRM task title must be 200 characters or fewer.')
    return value


def _clean_status(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in TASK_STATUSES:
        raise ValueError(f'Unknown CRM task status: {value}')
    return value


def _clean_priority(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in TASK_PRIORITIES:
        raise ValueError(f'Unknown CRM task priority: {value}')
    return value


def _clean_due_date(value: str) -> str:
    value = (value or '').strip()
    if not value:
        return ''
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError('CRM task due date must use YYYY-MM-DD.') from exc
    return parsed.isoformat()


def _validate_relationships(
    conn: sqlite3.Connection,
    organization_id: int,
    company_id: int | None,
    contact_id: int | None,
    opportunity_id: int | None,
) -> None:
    for table, record_id in (
        ('crm_v2_companies', company_id),
        ('crm_v2_contacts', contact_id),
        ('crm_v2_opportunities', opportunity_id),
    ):
        crm_tenancy.ensure_same_organization(
            conn,
            organization_id=organization_id,
            table=table,
            record_id=record_id,
        )

    contact_company_id = None
    if contact_id is not None:
        row = conn.execute(
            '''
            SELECT company_id FROM crm_v2_contacts
            WHERE id = ? AND organization_id = ?
            ''',
            (contact_id, organization_id),
        ).fetchone()
        contact_company_id = row['company_id'] if row else None
        if company_id is not None and contact_company_id is not None:
            if int(contact_company_id) != company_id:
                raise ValueError('CRM task company does not match the contact company.')

    if opportunity_id is None:
        return

    opportunity = conn.execute(
        '''
        SELECT company_id, contact_id
        FROM crm_v2_opportunities
        WHERE id = ? AND organization_id = ?
        ''',
        (opportunity_id, organization_id),
    ).fetchone()
    if opportunity is None:
        raise ValueError('CRM task opportunity is missing or belongs to another organization.')

    opportunity_company = opportunity['company_id']
    opportunity_contact = opportunity['contact_id']

    if company_id is not None and opportunity_company is not None:
        if company_id != int(opportunity_company):
            raise ValueError('CRM task company does not match the opportunity company.')
    if contact_id is not None and opportunity_contact is not None:
        if contact_id != int(opportunity_contact):
            raise ValueError('CRM task contact does not match the opportunity contact.')
    if contact_company_id is not None and opportunity_company is not None:
        if int(contact_company_id) != int(opportunity_company):
            raise ValueError(
                'CRM task contact company does not match the opportunity company.'
            )


def create_task(
    organization_slug: str,
    *,
    title: str,
    description: str = '',
    company_id: int | None = None,
    contact_id: int | None = None,
    opportunity_id: int | None = None,
    status: str = 'open',
    priority: str = 'normal',
    due_date: str = '',
) -> CrmTask:
    organization_id = _org_id(organization_slug)
    clean_title = _clean_title(title)
    clean_status = _clean_status(status)
    clean_priority = _clean_priority(priority)
    clean_due = _clean_due_date(due_date)
    ensure_schema()
    timestamp = tenant_auth.now()

    with tenant_auth.db() as conn:
        _validate_relationships(
            conn, organization_id, company_id, contact_id, opportunity_id
        )
        cursor = conn.execute(
            '''
            INSERT INTO crm_v2_tasks(
                organization_id, company_id, contact_id, opportunity_id,
                title, description, status, priority, due_date,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                organization_id, company_id, contact_id, opportunity_id,
                clean_title, description or '', clean_status, clean_priority,
                clean_due, timestamp, timestamp,
            ),
        )
        conn.commit()
        row = _select(conn, organization_id, int(cursor.lastrowid))
    return _from_row(row)


def get_task(organization_slug: str, task_id: int) -> CrmTask | None:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        row = _select(conn, organization_id, int(task_id))
    return _from_row(row) if row else None


def list_tasks(
    organization_slug: str,
    *,
    status: str | None = None,
    priority: str | None = None,
    company_id: int | None = None,
    contact_id: int | None = None,
    opportunity_id: int | None = None,
    include_archived: bool = False,
) -> list[CrmTask]:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        _validate_relationships(
            conn, organization_id, company_id, contact_id, opportunity_id
        )
        sql = '''
            SELECT t.*, o.slug AS organization_slug,
                   COALESCE(co.name, '') AS company_name,
                   COALESCE(c.name, '') AS contact_name,
                   COALESCE(op.title, '') AS opportunity_title
            FROM crm_v2_tasks t
            JOIN auth_organizations o ON o.id = t.organization_id
            LEFT JOIN crm_v2_companies co
              ON co.id = t.company_id AND co.organization_id = t.organization_id
            LEFT JOIN crm_v2_contacts c
              ON c.id = t.contact_id AND c.organization_id = t.organization_id
            LEFT JOIN crm_v2_opportunities op
              ON op.id = t.opportunity_id AND op.organization_id = t.organization_id
            WHERE t.organization_id = ?
        '''
        params: list[object] = [organization_id]
        if status is not None:
            sql += ' AND t.status = ?'
            params.append(_clean_status(status))
        elif not include_archived:
            sql += " AND t.status != 'archived'"
        if priority is not None:
            sql += ' AND t.priority = ?'
            params.append(_clean_priority(priority))
        if company_id is not None:
            sql += ' AND t.company_id = ?'
            params.append(company_id)
        if contact_id is not None:
            sql += ' AND t.contact_id = ?'
            params.append(contact_id)
        if opportunity_id is not None:
            sql += ' AND t.opportunity_id = ?'
            params.append(opportunity_id)
        sql += " ORDER BY CASE WHEN t.due_date = '' THEN 1 ELSE 0 END, t.due_date, t.id"
        rows = conn.execute(sql, params).fetchall()
    return [_from_row(row) for row in rows]


def update_task(
    organization_slug: str,
    task_id: int,
    *,
    title: str | None = None,
    description: str | None = None,
    company_id: int | None | object = ...,
    contact_id: int | None | object = ...,
    opportunity_id: int | None | object = ...,
    status: str | None = None,
    priority: str | None = None,
    due_date: str | None = None,
) -> CrmTask | None:
    organization_id = _org_id(organization_slug)
    ensure_schema()

    with tenant_auth.db() as conn:
        existing = _select(conn, organization_id, int(task_id))
        if existing is None:
            return None
        if existing['status'] == 'archived':
            raise ValueError('Archived CRM tasks cannot be updated.')

        next_company = existing['company_id'] if company_id is ... else company_id
        next_contact = existing['contact_id'] if contact_id is ... else contact_id
        next_opportunity = (
            existing['opportunity_id'] if opportunity_id is ... else opportunity_id
        )
        _validate_relationships(
            conn, organization_id, next_company, next_contact, next_opportunity
        )

        assignments: list[str] = []
        params: list[object] = []
        if title is not None:
            assignments.append('title = ?')
            params.append(_clean_title(title))
        if description is not None:
            assignments.append('description = ?')
            params.append(description)
        if company_id is not ...:
            assignments.append('company_id = ?')
            params.append(company_id)
        if contact_id is not ...:
            assignments.append('contact_id = ?')
            params.append(contact_id)
        if opportunity_id is not ...:
            assignments.append('opportunity_id = ?')
            params.append(opportunity_id)
        if status is not None:
            assignments.append('status = ?')
            params.append(_clean_status(status))
        if priority is not None:
            assignments.append('priority = ?')
            params.append(_clean_priority(priority))
        if due_date is not None:
            assignments.append('due_date = ?')
            params.append(_clean_due_date(due_date))

        if not assignments:
            return _from_row(existing)

        assignments.append('updated_at = ?')
        params.append(tenant_auth.now())
        params.extend([organization_id, int(task_id)])
        conn.execute(
            f'''
            UPDATE crm_v2_tasks
            SET {', '.join(assignments)}
            WHERE organization_id = ? AND id = ?
            ''',
            params,
        )
        conn.commit()
        row = _select(conn, organization_id, int(task_id))
    return _from_row(row)


def archive_task(organization_slug: str, task_id: int) -> CrmTask | None:
    task = get_task(organization_slug, task_id)
    if task is None:
        return None
    if task.status == 'archived':
        return task
    return update_task(organization_slug, task_id, status='archived')


def _select(conn: sqlite3.Connection, organization_id: int, task_id: int):
    return conn.execute(
        '''
        SELECT t.*, o.slug AS organization_slug,
               COALESCE(co.name, '') AS company_name,
               COALESCE(c.name, '') AS contact_name,
               COALESCE(op.title, '') AS opportunity_title
        FROM crm_v2_tasks t
        JOIN auth_organizations o ON o.id = t.organization_id
        LEFT JOIN crm_v2_companies co
          ON co.id = t.company_id AND co.organization_id = t.organization_id
        LEFT JOIN crm_v2_contacts c
          ON c.id = t.contact_id AND c.organization_id = t.organization_id
        LEFT JOIN crm_v2_opportunities op
          ON op.id = t.opportunity_id AND op.organization_id = t.organization_id
        WHERE t.organization_id = ? AND t.id = ?
        LIMIT 1
        ''',
        (organization_id, task_id),
    ).fetchone()


def _from_row(row) -> CrmTask:
    return CrmTask(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        company_id=int(row['company_id']) if row['company_id'] is not None else None,
        company_name=str(row['company_name']),
        contact_id=int(row['contact_id']) if row['contact_id'] is not None else None,
        contact_name=str(row['contact_name']),
        opportunity_id=(
            int(row['opportunity_id']) if row['opportunity_id'] is not None else None
        ),
        opportunity_title=str(row['opportunity_title']),
        title=str(row['title']),
        description=str(row['description']),
        status=str(row['status']),
        priority=str(row['priority']),
        due_date=str(row['due_date']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
