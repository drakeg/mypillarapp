from __future__ import annotations

from dataclasses import dataclass

import crm_companies
import crm_contacts
import crm_opportunities
import crm_tenancy
import tenant_auth


LEAD_STAGE_MAP = {
    'new': 'new',
    'contacted': 'qualified',
    'qualified': 'qualified',
    'proposal': 'proposal',
    'won': 'won',
    'lost': 'lost',
}


@dataclass(frozen=True)
class LegacyMigrationResult:
    companies_created: int
    contacts_created: int
    opportunities_created: int
    already_mapped: int


def ensure_schema() -> None:
    crm_opportunities.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS crm_v2_legacy_map (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                legacy_kind TEXT NOT NULL,
                legacy_id INTEGER NOT NULL,
                organization_id INTEGER NOT NULL,
                canonical_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                UNIQUE(legacy_kind, legacy_id),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE
            )
            '''
        )
        conn.commit()


def migrate_legacy_crm() -> LegacyMigrationResult:
    """Copy safe legacy CRM rows into canonical tables without changing legacy data.

    The migration is deliberately additive and idempotent. Existing canonical
    rows that were previously mapped are never overwritten on later runs.
    """
    audit = crm_tenancy.audit_legacy_crm()
    if not audit.safe_to_migrate:
        raise ValueError(
            'Legacy CRM audit is not safe to migrate: '
            f'unknown={audit.unknown_organization_rows}, '
            f'cross_tenant={audit.cross_tenant_links}, '
            f'missing={audit.missing_links}.'
        )

    ensure_schema()
    created_companies = 0
    created_contacts = 0
    created_opportunities = 0
    already_mapped = 0

    with tenant_auth.db() as conn:
        # Migration is only allowed for organizations that are currently active.
        inactive = conn.execute(
            '''
            SELECT COUNT(*) AS n
            FROM (
                SELECT organization_slug FROM crm_companies
                UNION
                SELECT organization_slug FROM crm_contacts
                UNION
                SELECT organization_slug FROM crm_leads
            ) legacy
            LEFT JOIN auth_organizations o ON o.slug = legacy.organization_slug
            WHERE o.id IS NULL OR o.status != 'active'
            '''
        ).fetchone()
        if int(inactive['n'] or 0):
            raise ValueError('Legacy CRM migration requires active organizations.')

        company_map: dict[int, int] = {}
        for row in conn.execute('SELECT * FROM crm_companies ORDER BY id').fetchall():
            mapped = _mapped_id(conn, 'company', int(row['id']))
            if mapped is not None:
                company_map[int(row['id'])] = mapped
                already_mapped += 1
                continue
            org_id = _organization_id(conn, str(row['organization_slug']))
            cur = conn.execute(
                '''
                INSERT INTO crm_v2_companies(
                    organization_id, name, website, industry, status, notes,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    org_id,
                    str(row['name']).strip(),
                    str(row['website'] or '').strip(),
                    str(row['industry'] or '').strip(),
                    _company_status(str(row['status'] or 'prospect')),
                    str(row['notes'] or ''),
                    int(row['created_at']),
                    int(row['updated_at']),
                ),
            )
            canonical_id = int(cur.lastrowid)
            _record_map(conn, 'company', int(row['id']), org_id, canonical_id)
            company_map[int(row['id'])] = canonical_id
            created_companies += 1

        contact_map: dict[int, int] = {}
        for row in conn.execute('SELECT * FROM crm_contacts ORDER BY id').fetchall():
            mapped = _mapped_id(conn, 'contact', int(row['id']))
            if mapped is not None:
                contact_map[int(row['id'])] = mapped
                already_mapped += 1
                continue
            org_id = _organization_id(conn, str(row['organization_slug']))
            company_id = (
                company_map[int(row['company_id'])]
                if row['company_id'] is not None else None
            )
            cur = conn.execute(
                '''
                INSERT INTO crm_v2_contacts(
                    organization_id, company_id, name, email, phone, title,
                    status, tags, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    org_id,
                    company_id,
                    str(row['name']).strip(),
                    str(row['email'] or '').strip().lower(),
                    _legacy_phone(str(row['phone'] or '')),
                    str(row['title'] or '').strip(),
                    _contact_status(str(row['status'] or 'lead')),
                    str(row['tags'] or '').strip(),
                    str(row['notes'] or ''),
                    int(row['created_at']),
                    int(row['updated_at']),
                ),
            )
            canonical_id = int(cur.lastrowid)
            _record_map(conn, 'contact', int(row['id']), org_id, canonical_id)
            contact_map[int(row['id'])] = canonical_id
            created_contacts += 1

        for row in conn.execute('SELECT * FROM crm_leads ORDER BY id').fetchall():
            mapped = _mapped_id(conn, 'lead', int(row['id']))
            if mapped is not None:
                already_mapped += 1
                continue
            org_id = _organization_id(conn, str(row['organization_slug']))
            company_id = (
                company_map[int(row['company_id'])]
                if row['company_id'] is not None else None
            )
            contact_id = (
                contact_map[int(row['contact_id'])]
                if row['contact_id'] is not None else None
            )
            source_note = (
                '[Legacy CRM migration]\n'
                f"source={str(row['source'] or '').strip()}\n"
                f"priority={str(row['priority'] or '').strip()}\n"
                f"value_estimate={str(row['value_estimate'] or '').strip()}"
            )
            notes = str(row['notes'] or '')
            if notes:
                notes = notes.rstrip() + '\n\n' + source_note
            else:
                notes = source_note
            cur = conn.execute(
                '''
                INSERT INTO crm_v2_opportunities(
                    organization_id, company_id, contact_id, title, stage, status,
                    value_cents, currency, expected_close_date, position, notes,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'active', 0, 'USD', '', 0, ?, ?, ?)
                ''',
                (
                    org_id,
                    company_id,
                    contact_id,
                    str(row['title']).strip(),
                    LEAD_STAGE_MAP.get(str(row['status'] or '').strip().lower(), 'new'),
                    notes,
                    int(row['created_at']),
                    int(row['updated_at']),
                ),
            )
            canonical_id = int(cur.lastrowid)
            _record_map(conn, 'lead', int(row['id']), org_id, canonical_id)
            created_opportunities += 1

        conn.commit()

    return LegacyMigrationResult(
        companies_created=created_companies,
        contacts_created=created_contacts,
        opportunities_created=created_opportunities,
        already_mapped=already_mapped,
    )


def _organization_id(conn, slug: str) -> int:
    row = conn.execute(
        "SELECT id FROM auth_organizations WHERE slug=? AND status='active'",
        ((slug or '').strip().lower(),),
    ).fetchone()
    if row is None:
        raise ValueError('Legacy CRM organization is missing or inactive.')
    return int(row['id'])


def _mapped_id(conn, legacy_kind: str, legacy_id: int) -> int | None:
    row = conn.execute(
        '''
        SELECT canonical_id FROM crm_v2_legacy_map
        WHERE legacy_kind=? AND legacy_id=?
        ''',
        (legacy_kind, legacy_id),
    ).fetchone()
    return int(row['canonical_id']) if row else None


def _record_map(conn, legacy_kind: str, legacy_id: int,
                organization_id: int, canonical_id: int) -> None:
    conn.execute(
        '''
        INSERT INTO crm_v2_legacy_map(
            legacy_kind, legacy_id, organization_id, canonical_id, created_at
        ) VALUES (?, ?, ?, ?, ?)
        ''',
        (legacy_kind, legacy_id, organization_id, canonical_id, tenant_auth.now()),
    )


def _company_status(value: str) -> str:
    value = (value or '').strip().lower()
    return value if value in {'prospect', 'customer', 'vendor', 'archived'} else 'prospect'


def _contact_status(value: str) -> str:
    value = (value or '').strip().lower()
    return value if value in {'lead', 'prospect', 'customer', 'vendor', 'archived'} else 'lead'


def _legacy_phone(value: str) -> str:
    value = (value or '').strip()
    if not value:
        return ''
    digits = ''.join(ch for ch in value if ch.isdigit())
    if 7 <= len(digits) <= 15:
        return ('+' if value.startswith('+') else '') + digits
    # Preserve legacy values rather than silently dropping them. Canonical
    # writes are validated going forward; migration compatibility is lossless.
    return value
