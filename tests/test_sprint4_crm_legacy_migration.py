from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import crm_companies
import crm_contacts
import crm_legacy_migration
import crm_opportunities
import platform_core
import tenant_auth


class Sprint4LegacyCrmMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        platform_core.DATA_DIR = data
        platform_core.DB_PATH = data / 'madmallard.sqlite3'
        with platform_core.db() as conn:
            platform_core.ensure_crm_schema(conn)

    def tearDown(self):
        self.tmp.cleanup()

    def seed_legacy(self):
        company_id = platform_core.crm_create_company(
            actor='test', name='Legacy Co', website='https://example.com',
            industry='Tech', organization_slug='solutions'
        )
        contact_id = platform_core.crm_create_contact(
            actor='test', name='Legacy Person', email='PERSON@EXAMPLE.COM',
            phone='814-555-1212', company_id=company_id,
            organization_slug='solutions'
        )
        lead_id = platform_core.crm_create_lead(
            actor='test', title='Legacy Deal', company_id=company_id,
            contact_id=contact_id, source='website', value_estimate='$12,500',
            status='proposal', priority='high', notes='Original note',
            organization_slug='solutions'
        )
        return company_id, contact_id, lead_id

    def test_migration_is_additive_and_maps_relationships(self):
        company_id, contact_id, lead_id = self.seed_legacy()
        result = crm_legacy_migration.migrate_legacy_crm()
        self.assertEqual(1, result.companies_created)
        self.assertEqual(1, result.contacts_created)
        self.assertEqual(1, result.opportunities_created)

        company = crm_companies.list_companies('solutions')[0]
        contact = crm_contacts.list_contacts('solutions')[0]
        opportunity = crm_opportunities.list_opportunities('solutions')[0]
        self.assertEqual(company.id, contact.company_id)
        self.assertEqual(company.id, opportunity.company_id)
        self.assertEqual(contact.id, opportunity.contact_id)
        self.assertEqual('proposal', opportunity.stage)
        self.assertEqual(0, opportunity.value_cents)
        self.assertIn('value_estimate=$12,500', opportunity.notes)

        with tenant_auth.db() as conn:
            self.assertIsNotNone(conn.execute(
                'SELECT 1 FROM crm_companies WHERE id=?', (company_id,)
            ).fetchone())
            self.assertIsNotNone(conn.execute(
                'SELECT 1 FROM crm_contacts WHERE id=?', (contact_id,)
            ).fetchone())
            self.assertIsNotNone(conn.execute(
                'SELECT 1 FROM crm_leads WHERE id=?', (lead_id,)
            ).fetchone())

    def test_second_run_is_idempotent_and_preserves_canonical_edits(self):
        self.seed_legacy()
        first = crm_legacy_migration.migrate_legacy_crm()
        company = crm_companies.list_companies('solutions')[0]
        crm_companies.update_company(
            'solutions', company.id, notes='Canonical owner edit'
        )
        second = crm_legacy_migration.migrate_legacy_crm()
        self.assertEqual((1, 1, 1), (
            first.companies_created, first.contacts_created,
            first.opportunities_created
        ))
        self.assertEqual(0, second.companies_created)
        self.assertEqual(0, second.contacts_created)
        self.assertEqual(0, second.opportunities_created)
        self.assertEqual(3, second.already_mapped)
        self.assertEqual(
            'Canonical owner edit',
            crm_companies.get_company('solutions', company.id).notes
        )

    def test_unsafe_legacy_audit_blocks_all_copying(self):
        company_id, _, _ = self.seed_legacy()
        with tenant_auth.db() as conn:
            conn.execute(
                "INSERT INTO crm_contacts(created_at,updated_at,organization_slug,company_id,name,email,phone,title,status,tags,notes) "
                "VALUES(1,1,'adventures',?,'Cross Tenant','','','','lead','','')",
                (company_id,),
            )
            conn.commit()
        with self.assertRaisesRegex(ValueError, 'not safe to migrate'):
            crm_legacy_migration.migrate_legacy_crm()
        self.assertEqual([], crm_companies.list_companies('solutions'))

    def test_inactive_legacy_organization_blocks_migration(self):
        self.seed_legacy()
        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_organizations SET status='suspended' WHERE slug='solutions'"
            )
            conn.commit()
        with self.assertRaisesRegex(ValueError, 'active organizations'):
            crm_legacy_migration.migrate_legacy_crm()

    def test_legacy_rows_are_not_rewritten(self):
        self.seed_legacy()
        with tenant_auth.db() as conn:
            before = tuple(conn.execute(
                'SELECT name,email,phone,status FROM crm_contacts ORDER BY id'
            ).fetchone())
        crm_legacy_migration.migrate_legacy_crm()
        with tenant_auth.db() as conn:
            after = tuple(conn.execute(
                'SELECT name,email,phone,status FROM crm_contacts ORDER BY id'
            ).fetchone())
        self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
