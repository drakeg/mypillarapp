from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import sqlite3

import crm_opportunities
import crm_tenancy
import tenant_auth


PROJECT_STATUSES = (
    'planned',
    'active',
    'on_hold',
    'completed',
    'canceled',
    'archived',
)


@dataclass(frozen=True)
class ServiceProject:
    id: int
    organization_id: int
    organization_slug: str
    customer_user_id: int
    customer_email: str
    company_id: int | None
    contact_id: int | None
    opportunity_id: int | None
    title: str
    summary: str
    status: str
    start_date: str
    due_date: str
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    crm_opportunities.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS portal_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                customer_user_id INTEGER NOT NULL,
                customer_email TEXT NOT NULL COLLATE NOCASE,
                company_id INTEGER,
                contact_id INTEGER,
                opportunity_id INTEGER,
                title TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'planned',
                start_date TEXT NOT NULL DEFAULT '',
                due_date TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                CHECK(status IN (
                    'planned','active','on_hold','completed','canceled','archived'
                )),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(customer_user_id)
                    REFERENCES auth_users(id) ON DELETE RESTRICT,
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
            'CREATE INDEX IF NOT EXISTS idx_portal_projects_org_status '
            'ON portal_projects(organization_id, status, updated_at DESC, id DESC)'
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_portal_projects_org_customer '
            'ON portal_projects(organization_id, customer_user_id, updated_at DESC, id DESC)'
        )
        conn.commit()


def _org_id(organization_slug: str) -> int:
    return crm_tenancy.organization_id(organization_slug)


def _clean_title(value: str) -> str:
    value = (value or '').strip()
    if not value:
        raise ValueError('Project title is required.')
    if len(value) > 200:
        raise ValueError('Project title must be 200 characters or fewer.')
    return value


def _clean_summary(value: str) -> str:
    value = (value or '').strip()
    if len(value) > 5000:
        raise ValueError('Project summary must be 5000 characters or fewer.')
    return value


def _clean_status(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in PROJECT_STATUSES:
        raise ValueError(f'Unknown project status: {value}')
    return value


def _clean_date(value: str, label: str) -> str:
    value = (value or '').strip()
    if not value:
        return ''
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f'{label} must use YYYY-MM-DD.') from exc


def _validate_customer(
    conn: sqlite3.Connection,
    organization_id: int,
    customer_user_id: int,
) -> str:
    if isinstance(customer_user_id, bool):
        raise ValueError('Project customer is invalid.')
    try:
        customer_user_id = int(customer_user_id)
    except (TypeError, ValueError) as exc:
        raise ValueError('Project customer is invalid.') from exc
    row = conn.execute(
        '''
        SELECT lower(u.email) AS email
        FROM auth_users u
        JOIN auth_memberships m
          ON m.user_id=u.id
         AND m.organization_id=u.organization_id
         AND m.status='active'
        WHERE u.id=? AND u.organization_id=? AND u.is_active=1
        ''',
        (customer_user_id, organization_id),
    ).fetchone()
    if row is None:
        raise ValueError('Project customer is missing, inactive, or belongs to another organization.')
    return str(row['email'])


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

    if contact_id is not None:
        contact = conn.execute(
            '''
            SELECT company_id FROM crm_v2_contacts
            WHERE id=? AND organization_id=?
            ''',
            (contact_id, organization_id),
        ).fetchone()
        if (
            company_id is not None
            and contact is not None
            and contact['company_id'] is not None
            and int(contact['company_id']) != company_id
        ):
            raise ValueError('Project company does not match the contact company.')

    if opportunity_id is not None:
        opportunity = conn.execute(
            '''
            SELECT company_id, contact_id FROM crm_v2_opportunities
            WHERE id=? AND organization_id=?
            ''',
            (opportunity_id, organization_id),
        ).fetchone()
        if opportunity is None:
            raise ValueError('Project opportunity is unavailable.')
        if (
            company_id is not None
            and opportunity['company_id'] is not None
            and int(opportunity['company_id']) != company_id
        ):
            raise ValueError('Project company does not match the opportunity company.')
        if (
            contact_id is not None
            and opportunity['contact_id'] is not None
            and int(opportunity['contact_id']) != contact_id
        ):
            raise ValueError('Project contact does not match the opportunity contact.')


def create_project(
    organization_slug: str,
    *,
    customer_user_id: int,
    title: str,
    summary: str = '',
    company_id: int | None = None,
    contact_id: int | None = None,
    opportunity_id: int | None = None,
    status: str = 'planned',
    start_date: str = '',
    due_date: str = '',
) -> ServiceProject:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        customer_email = _validate_customer(
            conn, organization_id, customer_user_id
        )
        _validate_relationships(
            conn, organization_id, company_id, contact_id, opportunity_id
        )
        clean_start = _clean_date(start_date, 'Project start date')
        clean_due = _clean_date(due_date, 'Project due date')
        if clean_start and clean_due and clean_due < clean_start:
            raise ValueError('Project due date cannot be before the start date.')
        cur = conn.execute(
            '''
            INSERT INTO portal_projects(
                organization_id, customer_user_id, customer_email,
                company_id, contact_id, opportunity_id,
                title, summary, status, start_date, due_date,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                organization_id,
                int(customer_user_id),
                customer_email,
                company_id,
                contact_id,
                opportunity_id,
                _clean_title(title),
                _clean_summary(summary),
                _clean_status(status),
                clean_start,
                clean_due,
                now,
                now,
            ),
        )
        conn.commit()
        row = _select(conn, organization_id, int(cur.lastrowid))
    return _from_row(row)


def get_project(
    organization_slug: str,
    project_id: int,
) -> ServiceProject | None:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        row = _select(conn, organization_id, int(project_id))
    return _from_row(row) if row else None


def list_projects(
    organization_slug: str,
    *,
    customer_user_id: int | None = None,
    status: str | None = None,
    include_archived: bool = False,
) -> list[ServiceProject]:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        if customer_user_id is not None:
            _validate_customer(conn, organization_id, customer_user_id)
        sql = '''
            SELECT p.*, o.slug AS organization_slug
            FROM portal_projects p
            JOIN auth_organizations o ON o.id=p.organization_id
            WHERE p.organization_id=?
        '''
        params: list[object] = [organization_id]
        if customer_user_id is not None:
            sql += ' AND p.customer_user_id=?'
            params.append(int(customer_user_id))
        if status is not None:
            sql += ' AND p.status=?'
            params.append(_clean_status(status))
        elif not include_archived:
            sql += " AND p.status!='archived'"
        sql += ' ORDER BY p.updated_at DESC, p.id DESC'
        rows = conn.execute(sql, params).fetchall()
    return [_from_row(row) for row in rows]


def update_project(
    organization_slug: str,
    project_id: int,
    *,
    title: str | None = None,
    summary: str | None = None,
    customer_user_id: int | None = None,
    company_id: int | None | object = ...,
    contact_id: int | None | object = ...,
    opportunity_id: int | None | object = ...,
    status: str | None = None,
    start_date: str | None = None,
    due_date: str | None = None,
) -> ServiceProject | None:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        existing = _select(conn, organization_id, int(project_id))
        if existing is None:
            return None
        if existing['status'] == 'archived':
            raise ValueError('Archived projects cannot be updated.')

        next_customer_id = (
            int(existing['customer_user_id'])
            if customer_user_id is None
            else int(customer_user_id)
        )
        next_customer_email = _validate_customer(
            conn, organization_id, next_customer_id
        )
        next_company = existing['company_id'] if company_id is ... else company_id
        next_contact = existing['contact_id'] if contact_id is ... else contact_id
        next_opportunity = (
            existing['opportunity_id']
            if opportunity_id is ...
            else opportunity_id
        )
        _validate_relationships(
            conn,
            organization_id,
            next_company,
            next_contact,
            next_opportunity,
        )

        next_start = (
            str(existing['start_date'])
            if start_date is None
            else _clean_date(start_date, 'Project start date')
        )
        next_due = (
            str(existing['due_date'])
            if due_date is None
            else _clean_date(due_date, 'Project due date')
        )
        if next_start and next_due and next_due < next_start:
            raise ValueError('Project due date cannot be before the start date.')

        assignments: list[str] = []
        params: list[object] = []
        if title is not None:
            assignments.append('title=?')
            params.append(_clean_title(title))
        if summary is not None:
            assignments.append('summary=?')
            params.append(_clean_summary(summary))
        if customer_user_id is not None:
            assignments.extend(['customer_user_id=?', 'customer_email=?'])
            params.extend([next_customer_id, next_customer_email])
        if company_id is not ...:
            assignments.append('company_id=?')
            params.append(company_id)
        if contact_id is not ...:
            assignments.append('contact_id=?')
            params.append(contact_id)
        if opportunity_id is not ...:
            assignments.append('opportunity_id=?')
            params.append(opportunity_id)
        if status is not None:
            assignments.append('status=?')
            params.append(_clean_status(status))
        if start_date is not None:
            assignments.append('start_date=?')
            params.append(next_start)
        if due_date is not None:
            assignments.append('due_date=?')
            params.append(next_due)

        if not assignments:
            return _from_row(existing)

        assignments.append('updated_at=?')
        params.append(tenant_auth.now())
        params.extend([organization_id, int(project_id)])
        conn.execute(
            f'''
            UPDATE portal_projects
            SET {', '.join(assignments)}
            WHERE organization_id=? AND id=?
            ''',
            params,
        )
        conn.commit()
        row = _select(conn, organization_id, int(project_id))
    return _from_row(row)


def archive_project(
    organization_slug: str,
    project_id: int,
) -> ServiceProject | None:
    project = get_project(organization_slug, project_id)
    if project is None:
        return None
    if project.status == 'archived':
        return project
    return update_project(
        organization_slug,
        project_id,
        status='archived',
    )


def _select(conn: sqlite3.Connection, organization_id: int, project_id: int):
    return conn.execute(
        '''
        SELECT p.*, o.slug AS organization_slug
        FROM portal_projects p
        JOIN auth_organizations o ON o.id=p.organization_id
        WHERE p.organization_id=? AND p.id=?
        LIMIT 1
        ''',
        (organization_id, project_id),
    ).fetchone()


def _from_row(row) -> ServiceProject:
    return ServiceProject(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        customer_user_id=int(row['customer_user_id']),
        customer_email=str(row['customer_email']),
        company_id=int(row['company_id']) if row['company_id'] is not None else None,
        contact_id=int(row['contact_id']) if row['contact_id'] is not None else None,
        opportunity_id=(
            int(row['opportunity_id'])
            if row['opportunity_id'] is not None else None
        ),
        title=str(row['title']),
        summary=str(row['summary']),
        status=str(row['status']),
        start_date=str(row['start_date']),
        due_date=str(row['due_date']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
