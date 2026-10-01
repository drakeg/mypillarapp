"""Canonical CRM organization boundary and read-only legacy-data audit.

New CRM models must store an organization_id referencing auth_organizations,
and enforce that every related record belongs to the same organization.
The legacy platform_core CRM tables remain untouched until S4-T10.
"""
from __future__ import annotations

from dataclasses import dataclass
import sqlite3

import tenant_auth


@dataclass(frozen=True)
class LegacyCrmAudit:
    companies: int
    contacts: int
    leads: int
    unknown_organization_rows: int
    cross_tenant_links: int
    missing_links: int

    @property
    def safe_to_migrate(self) -> bool:
        return not (self.unknown_organization_rows or
                    self.cross_tenant_links or self.missing_links)


def organization_id(organization_slug: str) -> int:
    slug = (organization_slug or '').strip().lower()
    with tenant_auth.db() as conn:
        row = conn.execute(
            "SELECT id FROM auth_organizations WHERE slug = ? AND status = 'active'",
            (slug,),
        ).fetchone()
    if row is None:
        raise ValueError('Active CRM organization not found.')
    return int(row['id'])


def ensure_same_organization(
    conn: sqlite3.Connection,
    *,
    organization_id: int,
    table: str,
    record_id: int | None,
) -> None:
    """Fail closed for absent or foreign relationships.

    Only explicitly registered canonical CRM tables are permitted; callers
    must not pass arbitrary SQL table identifiers.
    """
    allowed = frozenset({'crm_v2_companies', 'crm_v2_contacts', 'crm_v2_opportunities', 'crm_v2_tasks'})
    if table not in allowed:
        raise ValueError('Unsupported CRM relationship target.')
    if record_id is None:
        return
    if isinstance(record_id, bool) or not isinstance(record_id, int) or record_id <= 0:
        raise ValueError('Invalid CRM relationship ID.')
    row = conn.execute(
        f'SELECT organization_id FROM {table} WHERE id = ?',
        (record_id,),
    ).fetchone()
    if row is None or int(row['organization_id']) != organization_id:
        raise ValueError('CRM relationship is missing or belongs to another organization.')


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def audit_legacy_crm() -> LegacyCrmAudit:
    """Report legacy integrity without creating/migrating/changing legacy rows.

    An old contact may point to a company in another organization; likewise
    an old lead may reference a foreign contact or company. SQLite's existing
    simple foreign keys do not prohibit these cross-tenant associations.
    """
    tables = ('crm_companies', 'crm_contacts', 'crm_leads')
    with tenant_auth.db() as conn:
        present = {table for table in tables if _table_exists(conn, table)}
        counts = {
            table: (
                int(conn.execute(f'SELECT COUNT(*) AS n FROM {table}').fetchone()['n'])
                if table in present else 0
            )
            for table in tables
        }
        unknown = 0
        for table in present:
            unknown += int(conn.execute(
                f'''SELECT COUNT(*) AS n FROM {table} AS record
                    LEFT JOIN auth_organizations AS org
                      ON org.slug = record.organization_slug
                    WHERE org.id IS NULL'''
            ).fetchone()['n'])

        foreign = 0
        missing = 0
        relationships = (
            ('crm_contacts', 'company_id', 'crm_companies'),
            ('crm_leads', 'company_id', 'crm_companies'),
            ('crm_leads', 'contact_id', 'crm_contacts'),
        )
        for child_table, field, parent_table in relationships:
            if child_table not in present:
                continue
            if parent_table not in present:
                missing += int(conn.execute(
                    f'SELECT COUNT(*) AS n FROM {child_table} WHERE {field} IS NOT NULL'
                ).fetchone()['n'])
                continue
            row = conn.execute(
                f'''SELECT
                        SUM(CASE WHEN parent.id IS NULL THEN 1 ELSE 0 END) AS missing,
                        SUM(CASE WHEN parent.id IS NOT NULL
                                  AND parent.organization_slug != child.organization_slug
                                 THEN 1 ELSE 0 END) AS foreign_count
                    FROM {child_table} AS child
                    LEFT JOIN {parent_table} AS parent ON parent.id = child.{field}
                    WHERE child.{field} IS NOT NULL'''
            ).fetchone()
            missing += int(row['missing'] or 0)
            foreign += int(row['foreign_count'] or 0)
    return LegacyCrmAudit(
        companies=counts['crm_companies'],
        contacts=counts['crm_contacts'],
        leads=counts['crm_leads'],
        unknown_organization_rows=unknown,
        cross_tenant_links=foreign,
        missing_links=missing,
    )
