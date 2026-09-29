from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import sqlite3

import crm_companies
import crm_contacts
import crm_tenancy
import tenant_auth


OPPORTUNITY_STAGES = ('new', 'qualified', 'proposal', 'negotiation', 'won', 'lost')
OPPORTUNITY_STATUSES = ('active', 'archived')


@dataclass(frozen=True)
class Opportunity:
    id: int
    organization_id: int
    organization_slug: str
    company_id: int | None
    company_name: str
    contact_id: int | None
    contact_name: str
    title: str
    stage: str
    status: str
    value_cents: int
    currency: str
    expected_close_date: str
    position: int
    notes: str
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    crm_contacts.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS crm_v2_opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                company_id INTEGER,
                contact_id INTEGER,
                title TEXT NOT NULL,
                stage TEXT NOT NULL DEFAULT 'new',
                status TEXT NOT NULL DEFAULT 'active',
                value_cents INTEGER NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'USD',
                expected_close_date TEXT NOT NULL DEFAULT '',
                position INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                CHECK(stage IN ('new','qualified','proposal','negotiation','won','lost')),
                CHECK(status IN ('active','archived')),
                CHECK(value_cents >= 0),
                CHECK(position >= 0),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(company_id)
                    REFERENCES crm_v2_companies(id) ON DELETE SET NULL,
                FOREIGN KEY(contact_id)
                    REFERENCES crm_v2_contacts(id) ON DELETE SET NULL
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_crm_v2_opportunities_org_stage_position '
            'ON crm_v2_opportunities(organization_id, status, stage, position, id)'
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_crm_v2_opportunities_org_company '
            'ON crm_v2_opportunities(organization_id, company_id, id)'
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_crm_v2_opportunities_org_contact '
            'ON crm_v2_opportunities(organization_id, contact_id, id)'
        )
        conn.commit()


def _org_id(organization_slug: str) -> int:
    return crm_tenancy.organization_id(organization_slug)


def _clean_title(value: str) -> str:
    value = (value or '').strip()
    if not value:
        raise ValueError('Opportunity title is required.')
    if len(value) > 200:
        raise ValueError('Opportunity title must be 200 characters or fewer.')
    return value


def _clean_stage(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in OPPORTUNITY_STAGES:
        raise ValueError(f'Unknown opportunity stage: {value}')
    return value


def _clean_status(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in OPPORTUNITY_STATUSES:
        raise ValueError(f'Unknown opportunity status: {value}')
    return value


def _clean_value_cents(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError('Opportunity value must be a non-negative integer number of cents.')
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Opportunity value must be a non-negative integer number of cents.') from exc
    if value < 0:
        raise ValueError('Opportunity value cannot be negative.')
    return value


def _clean_currency(value: str) -> str:
    value = (value or 'USD').strip().upper()
    if len(value) != 3 or not value.isalpha():
        raise ValueError('Currency must be a three-letter code.')
    return value


def _clean_expected_close_date(value: str) -> str:
    value = (value or '').strip()
    if not value:
        return ''
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError('Expected close date must use YYYY-MM-DD.') from exc
    return parsed.isoformat()


def _clean_position(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError('Pipeline position must be a non-negative integer.')
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Pipeline position must be a non-negative integer.') from exc
    if value < 0:
        raise ValueError('Pipeline position cannot be negative.')
    return value


def _validate_relationships(
    conn: sqlite3.Connection,
    organization_id: int,
    company_id: int | None,
    contact_id: int | None,
) -> None:
    crm_tenancy.ensure_same_organization(
        conn,
        organization_id=organization_id,
        table='crm_v2_companies',
        record_id=company_id,
    )
    crm_tenancy.ensure_same_organization(
        conn,
        organization_id=organization_id,
        table='crm_v2_contacts',
        record_id=contact_id,
    )
    if company_id is not None and contact_id is not None:
        row = conn.execute(
            '''
            SELECT company_id
            FROM crm_v2_contacts
            WHERE id = ? AND organization_id = ?
            ''',
            (contact_id, organization_id),
        ).fetchone()
        if row and row['company_id'] is not None and int(row['company_id']) != company_id:
            raise ValueError('Opportunity company does not match the contact company.')


def create_opportunity(
    organization_slug: str,
    *,
    title: str,
    company_id: int | None = None,
    contact_id: int | None = None,
    stage: str = 'new',
    value_cents: int = 0,
    currency: str = 'USD',
    expected_close_date: str = '',
    position: int = 0,
    notes: str = '',
) -> Opportunity:
    organization_id = _org_id(organization_slug)
    clean_title = _clean_title(title)
    clean_stage = _clean_stage(stage)
    clean_value = _clean_value_cents(value_cents)
    clean_currency = _clean_currency(currency)
    clean_close = _clean_expected_close_date(expected_close_date)
    clean_position = _clean_position(position)
    ensure_schema()
    timestamp = tenant_auth.now()
    with tenant_auth.db() as conn:
        _validate_relationships(conn, organization_id, company_id, contact_id)
        cursor = conn.execute(
            '''
            INSERT INTO crm_v2_opportunities(
                organization_id, company_id, contact_id, title, stage, status,
                value_cents, currency, expected_close_date, position, notes,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                organization_id, company_id, contact_id, clean_title, clean_stage,
                clean_value, clean_currency, clean_close, clean_position, notes or '',
                timestamp, timestamp,
            ),
        )
        conn.commit()
        row = _select(conn, organization_id, int(cursor.lastrowid))
    return _from_row(row)


def get_opportunity(organization_slug: str, opportunity_id: int) -> Opportunity | None:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        row = _select(conn, organization_id, int(opportunity_id))
    return _from_row(row) if row else None


def list_opportunities(
    organization_slug: str,
    *,
    stage: str | None = None,
    company_id: int | None = None,
    contact_id: int | None = None,
    include_archived: bool = False,
) -> list[Opportunity]:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        _validate_relationships(conn, organization_id, company_id, contact_id)
        sql = '''
            SELECT op.*, o.slug AS organization_slug,
                   COALESCE(co.name, '') AS company_name,
                   COALESCE(c.name, '') AS contact_name
            FROM crm_v2_opportunities op
            JOIN auth_organizations o ON o.id = op.organization_id
            LEFT JOIN crm_v2_companies co
              ON co.id = op.company_id AND co.organization_id = op.organization_id
            LEFT JOIN crm_v2_contacts c
              ON c.id = op.contact_id AND c.organization_id = op.organization_id
            WHERE op.organization_id = ?
        '''
        params: list[object] = [organization_id]
        if not include_archived:
            sql += " AND op.status = 'active'"
        if stage is not None:
            sql += ' AND op.stage = ?'
            params.append(_clean_stage(stage))
        if company_id is not None:
            sql += ' AND op.company_id = ?'
            params.append(company_id)
        if contact_id is not None:
            sql += ' AND op.contact_id = ?'
            params.append(contact_id)
        sql += ' ORDER BY op.stage, op.position, op.id'
        rows = conn.execute(sql, params).fetchall()
    return [_from_row(row) for row in rows]


def update_opportunity(
    organization_slug: str,
    opportunity_id: int,
    *,
    title: str | None = None,
    company_id: int | None | object = ...,
    contact_id: int | None | object = ...,
    stage: str | None = None,
    value_cents: int | None = None,
    currency: str | None = None,
    expected_close_date: str | None = None,
    position: int | None = None,
    notes: str | None = None,
) -> Opportunity | None:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        existing = _select(conn, organization_id, int(opportunity_id))
        if existing is None:
            return None
        if existing['status'] == 'archived':
            raise ValueError('Archived opportunities cannot be updated.')

        next_company = existing['company_id'] if company_id is ... else company_id
        next_contact = existing['contact_id'] if contact_id is ... else contact_id
        _validate_relationships(conn, organization_id, next_company, next_contact)

        assignments: list[str] = []
        params: list[object] = []
        if title is not None:
            assignments.append('title = ?')
            params.append(_clean_title(title))
        if company_id is not ...:
            assignments.append('company_id = ?')
            params.append(company_id)
        if contact_id is not ...:
            assignments.append('contact_id = ?')
            params.append(contact_id)
        if stage is not None:
            assignments.append('stage = ?')
            params.append(_clean_stage(stage))
        if value_cents is not None:
            assignments.append('value_cents = ?')
            params.append(_clean_value_cents(value_cents))
        if currency is not None:
            assignments.append('currency = ?')
            params.append(_clean_currency(currency))
        if expected_close_date is not None:
            assignments.append('expected_close_date = ?')
            params.append(_clean_expected_close_date(expected_close_date))
        if position is not None:
            assignments.append('position = ?')
            params.append(_clean_position(position))
        if notes is not None:
            assignments.append('notes = ?')
            params.append(notes)

        if not assignments:
            return _from_row(existing)

        assignments.append('updated_at = ?')
        params.append(tenant_auth.now())
        params.extend([organization_id, int(opportunity_id)])
        conn.execute(
            f'''
            UPDATE crm_v2_opportunities
            SET {', '.join(assignments)}
            WHERE organization_id = ? AND id = ?
            ''',
            params,
        )
        conn.commit()
        row = _select(conn, organization_id, int(opportunity_id))
    return _from_row(row)


def archive_opportunity(
    organization_slug: str,
    opportunity_id: int,
) -> Opportunity | None:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        existing = _select(conn, organization_id, int(opportunity_id))
        if existing is None:
            return None
        if existing['status'] == 'archived':
            return _from_row(existing)
        conn.execute(
            '''
            UPDATE crm_v2_opportunities
            SET status='archived', updated_at=?
            WHERE organization_id=? AND id=?
            ''',
            (tenant_auth.now(), organization_id, int(opportunity_id)),
        )
        conn.commit()
        row = _select(conn, organization_id, int(opportunity_id))
    return _from_row(row)


def _select(conn: sqlite3.Connection, organization_id: int, opportunity_id: int):
    return conn.execute(
        '''
        SELECT op.*, o.slug AS organization_slug,
               COALESCE(co.name, '') AS company_name,
               COALESCE(c.name, '') AS contact_name
        FROM crm_v2_opportunities op
        JOIN auth_organizations o ON o.id = op.organization_id
        LEFT JOIN crm_v2_companies co
          ON co.id = op.company_id AND co.organization_id = op.organization_id
        LEFT JOIN crm_v2_contacts c
          ON c.id = op.contact_id AND c.organization_id = op.organization_id
        WHERE op.organization_id = ? AND op.id = ?
        LIMIT 1
        ''',
        (organization_id, opportunity_id),
    ).fetchone()


def _from_row(row) -> Opportunity:
    return Opportunity(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        company_id=int(row['company_id']) if row['company_id'] is not None else None,
        company_name=str(row['company_name']),
        contact_id=int(row['contact_id']) if row['contact_id'] is not None else None,
        contact_name=str(row['contact_name']),
        title=str(row['title']),
        stage=str(row['stage']),
        status=str(row['status']),
        value_cents=int(row['value_cents']),
        currency=str(row['currency']),
        expected_close_date=str(row['expected_close_date']),
        position=int(row['position']),
        notes=str(row['notes']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
