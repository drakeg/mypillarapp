from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import crm_tenancy
import tenant_auth


class Sprint4CrmTenantBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        tenant_auth.DATA_DIR = Path(self.temp.name)
        tenant_auth.DB_PATH = tenant_auth.DATA_DIR / 'madmallard.sqlite3'

    def tearDown(self):
        self.temp.cleanup()

    def test_active_organization_lookup(self):
        self.assertEqual(
            crm_tenancy.organization_id('solutions'),
            crm_tenancy.organization_id(' SOLUTIONS '),
        )
        with self.assertRaises(ValueError):
            crm_tenancy.organization_id('unknown')

    def test_suspended_organization_is_not_a_write_target(self):
        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_organizations SET status='suspended' WHERE slug='solutions'"
            )
            conn.commit()
        with self.assertRaises(ValueError):
            crm_tenancy.organization_id('solutions')

    def test_relationship_boundary_fails_closed(self):
        with tenant_auth.db() as conn:
            conn.execute(
                'CREATE TABLE crm_v2_companies (id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL)'
            )
            conn.execute(
                "INSERT INTO crm_v2_companies(id, organization_id) "
                "SELECT 1, id FROM auth_organizations WHERE slug='solutions'"
            )
            solutions_id = int(conn.execute("SELECT id FROM auth_organizations WHERE slug='solutions'").fetchone()[0])
            other_id = int(conn.execute("SELECT id FROM auth_organizations WHERE slug='adventures'").fetchone()[0])
            crm_tenancy.ensure_same_organization(
                conn, organization_id=solutions_id,
                table='crm_v2_companies', record_id=1,
            )
            crm_tenancy.ensure_same_organization(
                conn, organization_id=solutions_id,
                table='crm_v2_companies', record_id=None,
            )
            with self.assertRaises(ValueError):
                crm_tenancy.ensure_same_organization(
                    conn, organization_id=other_id,
                    table='crm_v2_companies', record_id=1,
                )
            with self.assertRaises(ValueError):
                crm_tenancy.ensure_same_organization(
                    conn, organization_id=solutions_id,
                    table='crm_v2_companies', record_id=2,
                )
            with self.assertRaises(ValueError):
                crm_tenancy.ensure_same_organization(
                    conn, organization_id=solutions_id,
                    table='crm_companies; DROP TABLE auth_users',
                    record_id=1,
                )

    def test_missing_legacy_tables_are_safe_to_audit(self):
        audit = crm_tenancy.audit_legacy_crm()
        self.assertEqual((0, 0, 0), (audit.companies, audit.contacts, audit.leads))
        self.assertTrue(audit.safe_to_migrate)

    def test_legacy_audit_detects_unknown_org_cross_tenant_and_missing_links(self):
        with tenant_auth.db() as conn:
            conn.execute(
                '''CREATE TABLE crm_companies (
                       id INTEGER PRIMARY KEY, organization_slug TEXT NOT NULL
                   )'''
            )
            conn.execute(
                '''CREATE TABLE crm_contacts (
                       id INTEGER PRIMARY KEY, organization_slug TEXT NOT NULL,
                       company_id INTEGER
                   )'''
            )
            conn.execute(
                '''CREATE TABLE crm_leads (
                       id INTEGER PRIMARY KEY, organization_slug TEXT NOT NULL,
                       company_id INTEGER, contact_id INTEGER
                   )'''
            )
            conn.executemany(
                'INSERT INTO crm_companies VALUES (?,?)',
                [(1,'solutions'), (2,'adventures'), (3,'unknown-tenant')],
            )
            conn.executemany(
                'INSERT INTO crm_contacts VALUES (?,?,?)',
                [(1,'solutions',1), (2,'adventures',1), (3,'solutions',999)],
            )
            conn.executemany(
                'INSERT INTO crm_leads VALUES (?,?,?,?)',
                [(1,'solutions',2,2), (2,'solutions',1,999)],
            )
            conn.commit()
        audit = crm_tenancy.audit_legacy_crm()
        self.assertEqual((3,3,2), (audit.companies,audit.contacts,audit.leads))
        self.assertEqual(1, audit.unknown_organization_rows)
        self.assertEqual(3, audit.cross_tenant_links)
        self.assertEqual(2, audit.missing_links)
        self.assertFalse(audit.safe_to_migrate)
        with tenant_auth.db() as conn:
            self.assertEqual(3, conn.execute('SELECT COUNT(*) FROM crm_companies').fetchone()[0])


if __name__ == '__main__':
    unittest.main()
