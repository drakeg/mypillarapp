from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import crm_companies
import tenant_auth


class Sprint4CrmCompanyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        tenant_auth.DATA_DIR = Path(self.temp.name)
        tenant_auth.DB_PATH = tenant_auth.DATA_DIR / 'madmallard.sqlite3'

    def tearDown(self):
        self.temp.cleanup()

    def test_company_crud_is_tenant_scoped(self):
        company = crm_companies.create_company(
            'solutions',
            name='Acme LLC',
            website='https://acme.example',
            industry='Technology',
            notes='Important account',
        )
        self.assertEqual('solutions', company.organization_slug)
        self.assertEqual('prospect', company.status)
        self.assertEqual(company.id, crm_companies.get_company('solutions', company.id).id)
        self.assertIsNone(crm_companies.get_company('adventures', company.id))

        updated = crm_companies.update_company(
            'solutions',
            company.id,
            status='customer',
            industry='Cloud',
        )
        self.assertEqual('customer', updated.status)
        self.assertEqual('Cloud', updated.industry)

    def test_same_company_name_can_exist_in_different_tenants(self):
        first = crm_companies.create_company('solutions', name='Shared Name')
        second = crm_companies.create_company('adventures', name='Shared Name')
        self.assertNotEqual(first.organization_id, second.organization_id)
        self.assertEqual(1, len(crm_companies.list_companies('solutions')))
        self.assertEqual(1, len(crm_companies.list_companies('adventures')))

    def test_foreign_tenant_update_and_archive_do_not_mutate(self):
        company = crm_companies.create_company('solutions', name='Protected')
        self.assertIsNone(
            crm_companies.update_company('adventures', company.id, name='Wrong')
        )
        self.assertIsNone(crm_companies.archive_company('adventures', company.id))
        self.assertEqual('Protected', crm_companies.get_company('solutions', company.id).name)
        self.assertEqual('prospect', crm_companies.get_company('solutions', company.id).status)

    def test_archived_company_hidden_and_immutable(self):
        company = crm_companies.create_company('solutions', name='Old Co')
        archived = crm_companies.archive_company('solutions', company.id)
        self.assertEqual('archived', archived.status)
        self.assertEqual([], crm_companies.list_companies('solutions'))
        self.assertEqual(
            [company.id],
            [c.id for c in crm_companies.list_companies('solutions', include_archived=True)],
        )
        with self.assertRaises(ValueError):
            crm_companies.update_company('solutions', company.id, notes='No')

    def test_validation_rejects_bad_name_url_and_status(self):
        with self.assertRaises(ValueError):
            crm_companies.create_company('solutions', name='')
        with self.assertRaises(ValueError):
            crm_companies.create_company(
                'solutions', name='Bad URL', website='javascript:alert(1)'
            )
        with self.assertRaises(ValueError):
            crm_companies.create_company(
                'solutions', name='Bad Status', status='deleted'
            )

    def test_search_and_status_filters_remain_tenant_scoped(self):
        crm_companies.create_company(
            'solutions', name='Alpha Cloud', industry='Technology', status='prospect'
        )
        crm_companies.create_company(
            'solutions', name='Beta Fitness', industry='Wellness', status='customer'
        )
        crm_companies.create_company(
            'adventures', name='Alpha Travel', industry='Travel', status='prospect'
        )
        self.assertEqual(
            ['Alpha Cloud'],
            [c.name for c in crm_companies.list_companies('solutions', query='Alpha')],
        )
        self.assertEqual(
            ['Beta Fitness'],
            [c.name for c in crm_companies.list_companies('solutions', status='customer')],
        )

    def test_search_treats_wildcards_as_literal_text(self):
        crm_companies.create_company('solutions', name='Percent % Co')
        crm_companies.create_company('solutions', name='Ordinary Co')
        self.assertEqual(
            ['Percent % Co'],
            [c.name for c in crm_companies.list_companies('solutions', query='%')],
        )

    def test_inactive_tenant_cannot_access_company_model(self):
        crm_companies.create_company('solutions', name='Before suspension')
        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_organizations SET status='suspended' WHERE slug='solutions'"
            )
            conn.commit()
        with self.assertRaises(ValueError):
            crm_companies.list_companies('solutions')
        with self.assertRaises(ValueError):
            crm_companies.create_company('solutions', name='Blocked')


if __name__ == '__main__':
    unittest.main()
