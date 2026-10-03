from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import sqlite3

import crm_opportunities
import crm_tenancy
import tenant_auth


QUOTE_STATUSES = ('draft', 'sent', 'accepted', 'declined', 'archived')


@dataclass(frozen=True)
class Quote:
    id: int
    organization_id: int
    organization_slug: str
    company_id: int | None
    contact_id: int | None
    opportunity_id: int | None
    title: str
    status: str
    currency: str
    valid_until: str
    notes: str
    subtotal_cents: int
    created_at: int
    updated_at: int


@dataclass(frozen=True)
class QuoteLine:
    id: int
    organization_id: int
    quote_id: int
    description: str
    quantity: int
    unit_price_cents: int
    position: int
    line_total_cents: int
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    crm_opportunities.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS crm_v2_quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                company_id INTEGER,
                contact_id INTEGER,
                opportunity_id INTEGER,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                currency TEXT NOT NULL DEFAULT 'USD',
                valid_until TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                CHECK(status IN ('draft','sent','accepted','declined','archived')),
                FOREIGN KEY(organization_id) REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(company_id) REFERENCES crm_v2_companies(id) ON DELETE SET NULL,
                FOREIGN KEY(contact_id) REFERENCES crm_v2_contacts(id) ON DELETE SET NULL,
                FOREIGN KEY(opportunity_id) REFERENCES crm_v2_opportunities(id) ON DELETE SET NULL
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS crm_v2_quote_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                quote_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                unit_price_cents INTEGER NOT NULL DEFAULT 0,
                position INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                CHECK(quantity > 0),
                CHECK(unit_price_cents >= 0),
                CHECK(position >= 0),
                FOREIGN KEY(organization_id) REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(quote_id) REFERENCES crm_v2_quotes(id) ON DELETE CASCADE
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_crm_v2_quotes_org_status '
            'ON crm_v2_quotes(organization_id, status, updated_at DESC, id DESC)'
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_crm_v2_quote_lines_org_quote_position '
            'ON crm_v2_quote_lines(organization_id, quote_id, position, id)'
        )
        conn.commit()


def _org_id(slug: str) -> int:
    return crm_tenancy.organization_id(slug)


def _clean_title(value: str) -> str:
    value = (value or '').strip()
    if not value:
        raise ValueError('Quote title is required.')
    if len(value) > 200:
        raise ValueError('Quote title must be 200 characters or fewer.')
    return value


def _clean_description(value: str) -> str:
    value = (value or '').strip()
    if not value:
        raise ValueError('Quote line description is required.')
    if len(value) > 500:
        raise ValueError('Quote line description must be 500 characters or fewer.')
    return value


def _clean_status(value: str) -> str:
    value = (value or '').strip().lower()
    if value not in QUOTE_STATUSES:
        raise ValueError(f'Unknown quote status: {value}')
    return value


def _clean_currency(value: str) -> str:
    value = (value or 'USD').strip().upper()
    if len(value) != 3 or not value.isalpha():
        raise ValueError('Currency must be a three-letter code.')
    return value


def _clean_date(value: str) -> str:
    value = (value or '').strip()
    if not value:
        return ''
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError('Quote valid-until date must use YYYY-MM-DD.') from exc


def _clean_non_negative_int(value: int, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f'{label} must be a non-negative integer.')
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label} must be a non-negative integer.') from exc
    if value < 0:
        raise ValueError(f'{label} must be a non-negative integer.')
    return value


def _clean_positive_int(value: int, label: str) -> int:
    value = _clean_non_negative_int(value, label)
    if value == 0:
        raise ValueError(f'{label} must be greater than zero.')
    return value


def _validate_relationships(conn: sqlite3.Connection, organization_id: int,
                            company_id: int | None, contact_id: int | None,
                            opportunity_id: int | None) -> None:
    for table, record_id in (
        ('crm_v2_companies', company_id),
        ('crm_v2_contacts', contact_id),
        ('crm_v2_opportunities', opportunity_id),
    ):
        crm_tenancy.ensure_same_organization(
            conn, organization_id=organization_id, table=table, record_id=record_id
        )

    if company_id is not None and contact_id is not None:
        row = conn.execute(
            'SELECT company_id FROM crm_v2_contacts WHERE id=? AND organization_id=?',
            (contact_id, organization_id),
        ).fetchone()
        if row and row['company_id'] is not None and int(row['company_id']) != company_id:
            raise ValueError('Quote company does not match the contact company.')

    if opportunity_id is not None:
        row = conn.execute(
            'SELECT company_id, contact_id FROM crm_v2_opportunities WHERE id=? AND organization_id=?',
            (opportunity_id, organization_id),
        ).fetchone()
        if row is None:
            raise ValueError('Quote opportunity is unavailable.')
        if company_id is not None and row['company_id'] is not None and int(row['company_id']) != company_id:
            raise ValueError('Quote company does not match the opportunity company.')
        if contact_id is not None and row['contact_id'] is not None and int(row['contact_id']) != contact_id:
            raise ValueError('Quote contact does not match the opportunity contact.')


def create_quote(organization_slug: str, *, title: str,
                 company_id: int | None = None, contact_id: int | None = None,
                 opportunity_id: int | None = None, currency: str = 'USD',
                 valid_until: str = '', notes: str = '') -> Quote:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        _validate_relationships(conn, organization_id, company_id, contact_id, opportunity_id)
        cur = conn.execute(
            '''
            INSERT INTO crm_v2_quotes(
                organization_id, company_id, contact_id, opportunity_id,
                title, status, currency, valid_until, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?)
            ''',
            (organization_id, company_id, contact_id, opportunity_id,
             _clean_title(title), _clean_currency(currency), _clean_date(valid_until),
             notes or '', now, now),
        )
        conn.commit()
        row = _select_quote(conn, organization_id, int(cur.lastrowid))
    return _from_quote(row)


def add_line(organization_slug: str, quote_id: int, *, description: str,
             quantity: int = 1, unit_price_cents: int = 0, position: int = 0) -> QuoteLine:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        quote = _select_quote(conn, organization_id, int(quote_id))
        if quote is None:
            raise ValueError('Quote is missing or belongs to another organization.')
        if quote['status'] != 'draft':
            raise ValueError('Only draft quotes can be modified.')
        cur = conn.execute(
            '''
            INSERT INTO crm_v2_quote_lines(
                organization_id, quote_id, description, quantity,
                unit_price_cents, position, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (organization_id, int(quote_id), _clean_description(description),
             _clean_positive_int(quantity, 'Quantity'),
             _clean_non_negative_int(unit_price_cents, 'Unit price'),
             _clean_non_negative_int(position, 'Line position'), now, now),
        )
        conn.execute('UPDATE crm_v2_quotes SET updated_at=? WHERE organization_id=? AND id=?',
                     (now, organization_id, int(quote_id)))
        conn.commit()
        row = _select_line(conn, organization_id, int(cur.lastrowid))
    return _from_line(row)


def list_lines(organization_slug: str, quote_id: int) -> list[QuoteLine]:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        if _select_quote(conn, organization_id, int(quote_id)) is None:
            return []
        rows = conn.execute(
            '''
            SELECT * FROM crm_v2_quote_lines
            WHERE organization_id=? AND quote_id=?
            ORDER BY position, id
            ''',
            (organization_id, int(quote_id)),
        ).fetchall()
    return [_from_line(row) for row in rows]


def get_quote(organization_slug: str, quote_id: int) -> Quote | None:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        row = _select_quote(conn, organization_id, int(quote_id))
    return _from_quote(row) if row else None


def set_quote_status(organization_slug: str, quote_id: int, status: str) -> Quote | None:
    organization_id = _org_id(organization_slug)
    ensure_schema()
    clean_status = _clean_status(status)
    with tenant_auth.db() as conn:
        existing = _select_quote(conn, organization_id, int(quote_id))
        if existing is None:
            return None
        if existing['status'] == 'archived':
            raise ValueError('Archived quotes cannot be modified.')
        conn.execute(
            'UPDATE crm_v2_quotes SET status=?, updated_at=? WHERE organization_id=? AND id=?',
            (clean_status, tenant_auth.now(), organization_id, int(quote_id)),
        )
        conn.commit()
        row = _select_quote(conn, organization_id, int(quote_id))
    return _from_quote(row)


def _select_quote(conn: sqlite3.Connection, organization_id: int, quote_id: int):
    return conn.execute(
        '''
        SELECT q.*, o.slug AS organization_slug,
               COALESCE(SUM(l.quantity * l.unit_price_cents), 0) AS subtotal_cents
        FROM crm_v2_quotes q
        JOIN auth_organizations o ON o.id=q.organization_id
        LEFT JOIN crm_v2_quote_lines l
          ON l.organization_id=q.organization_id AND l.quote_id=q.id
        WHERE q.organization_id=? AND q.id=?
        GROUP BY q.id
        ''',
        (organization_id, quote_id),
    ).fetchone()


def _select_line(conn: sqlite3.Connection, organization_id: int, line_id: int):
    return conn.execute(
        'SELECT * FROM crm_v2_quote_lines WHERE organization_id=? AND id=?',
        (organization_id, line_id),
    ).fetchone()


def _from_quote(row) -> Quote:
    return Quote(
        id=int(row['id']), organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        company_id=int(row['company_id']) if row['company_id'] is not None else None,
        contact_id=int(row['contact_id']) if row['contact_id'] is not None else None,
        opportunity_id=int(row['opportunity_id']) if row['opportunity_id'] is not None else None,
        title=str(row['title']), status=str(row['status']), currency=str(row['currency']),
        valid_until=str(row['valid_until']), notes=str(row['notes']),
        subtotal_cents=int(row['subtotal_cents']),
        created_at=int(row['created_at']), updated_at=int(row['updated_at']),
    )


def _from_line(row) -> QuoteLine:
    quantity = int(row['quantity'])
    unit_price = int(row['unit_price_cents'])
    return QuoteLine(
        id=int(row['id']), organization_id=int(row['organization_id']),
        quote_id=int(row['quote_id']), description=str(row['description']),
        quantity=quantity, unit_price_cents=unit_price,
        position=int(row['position']), line_total_cents=quantity * unit_price,
        created_at=int(row['created_at']), updated_at=int(row['updated_at']),
    )
