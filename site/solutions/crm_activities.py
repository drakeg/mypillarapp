from __future__ import annotations

from dataclasses import dataclass
import sqlite3

import crm_tasks
import crm_tenancy
import tenant_auth


ACTIVITY_KINDS = ('note', 'status', 'email', 'call', 'meeting', 'system')


@dataclass(frozen=True)
class Activity:
    id: int
    organization_id: int
    organization_slug: str
    kind: str
    actor: str
    body: str
    company_id: int | None
    contact_id: int | None
    opportunity_id: int | None
    task_id: int | None
    created_at: int


def ensure_schema() -> None:
    crm_tasks.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS crm_v2_activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                kind TEXT NOT NULL DEFAULT 'note',
                actor TEXT NOT NULL,
                body TEXT NOT NULL,
                company_id INTEGER,
                contact_id INTEGER,
                opportunity_id INTEGER,
                task_id INTEGER,
                created_at INTEGER NOT NULL,
                CHECK(kind IN ('note','status','email','call','meeting','system')),
                FOREIGN KEY(organization_id) REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(company_id) REFERENCES crm_v2_companies(id) ON DELETE SET NULL,
                FOREIGN KEY(contact_id) REFERENCES crm_v2_contacts(id) ON DELETE SET NULL,
                FOREIGN KEY(opportunity_id) REFERENCES crm_v2_opportunities(id) ON DELETE SET NULL,
                FOREIGN KEY(task_id) REFERENCES crm_v2_tasks(id) ON DELETE SET NULL
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_crm_v2_activities_org_created '
            'ON crm_v2_activities(organization_id, created_at DESC, id DESC)'
        )
        conn.commit()


def _clean_kind(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in ACTIVITY_KINDS:
        raise ValueError(f'Unknown CRM activity kind: {value}')
    return value


def _clean_required(value: str, label: str, limit: int) -> str:
    value = (value or '').strip()
    if not value:
        raise ValueError(f'{label} is required.')
    if len(value) > limit:
        raise ValueError(f'{label} must be {limit} characters or fewer.')
    return value


def _validate_links(conn: sqlite3.Connection, organization_id: int, **links) -> None:
    mapping = {
        'company_id': 'crm_v2_companies',
        'contact_id': 'crm_v2_contacts',
        'opportunity_id': 'crm_v2_opportunities',
        'task_id': 'crm_v2_tasks',
    }
    for field, table in mapping.items():
        crm_tenancy.ensure_same_organization(
            conn, organization_id=organization_id,
            table=table, record_id=links.get(field)
        )


def add_activity(
    organization_slug: str,
    *,
    actor: str,
    body: str,
    kind: str = 'note',
    company_id: int | None = None,
    contact_id: int | None = None,
    opportunity_id: int | None = None,
    task_id: int | None = None,
) -> Activity:
    organization_id = crm_tenancy.organization_id(organization_slug)
    clean_actor = _clean_required(actor, 'Activity actor', 200)
    clean_body = _clean_required(body, 'Activity body', 5000)
    clean_kind = _clean_kind(kind)
    ensure_schema()
    with tenant_auth.db() as conn:
        _validate_links(
            conn, organization_id,
            company_id=company_id, contact_id=contact_id,
            opportunity_id=opportunity_id, task_id=task_id,
        )
        cur = conn.execute(
            '''
            INSERT INTO crm_v2_activities(
                organization_id, kind, actor, body,
                company_id, contact_id, opportunity_id, task_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                organization_id, clean_kind, clean_actor, clean_body,
                company_id, contact_id, opportunity_id, task_id, tenant_auth.now()
            ),
        )
        conn.commit()
        row = _select(conn, organization_id, int(cur.lastrowid))
    return _from_row(row)


def list_activities(
    organization_slug: str,
    *,
    company_id: int | None = None,
    contact_id: int | None = None,
    opportunity_id: int | None = None,
    task_id: int | None = None,
    kind: str | None = None,
    limit: int = 100,
) -> list[Activity]:
    organization_id = crm_tenancy.organization_id(organization_slug)
    ensure_schema()
    if limit < 1 or limit > 500:
        raise ValueError('Activity limit must be between 1 and 500.')
    with tenant_auth.db() as conn:
        _validate_links(
            conn, organization_id,
            company_id=company_id, contact_id=contact_id,
            opportunity_id=opportunity_id, task_id=task_id,
        )
        sql = 'SELECT a.*, o.slug AS organization_slug FROM crm_v2_activities a JOIN auth_organizations o ON o.id=a.organization_id WHERE a.organization_id=?'
        params: list[object] = [organization_id]
        for field, value in (
            ('company_id', company_id), ('contact_id', contact_id),
            ('opportunity_id', opportunity_id), ('task_id', task_id),
        ):
            if value is not None:
                sql += f' AND a.{field}=?'
                params.append(value)
        if kind is not None:
            sql += ' AND a.kind=?'
            params.append(_clean_kind(kind))
        sql += ' ORDER BY a.created_at DESC, a.id DESC LIMIT ?'
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    return [_from_row(row) for row in rows]


def _select(conn: sqlite3.Connection, organization_id: int, activity_id: int):
    return conn.execute(
        'SELECT a.*, o.slug AS organization_slug FROM crm_v2_activities a JOIN auth_organizations o ON o.id=a.organization_id WHERE a.organization_id=? AND a.id=?',
        (organization_id, activity_id),
    ).fetchone()


def _from_row(row) -> Activity:
    return Activity(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        kind=str(row['kind']),
        actor=str(row['actor']),
        body=str(row['body']),
        company_id=int(row['company_id']) if row['company_id'] is not None else None,
        contact_id=int(row['contact_id']) if row['contact_id'] is not None else None,
        opportunity_id=int(row['opportunity_id']) if row['opportunity_id'] is not None else None,
        task_id=int(row['task_id']) if row['task_id'] is not None else None,
        created_at=int(row['created_at']),
    )
