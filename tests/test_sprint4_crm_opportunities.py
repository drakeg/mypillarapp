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
import crm_opportunities
import tenant_auth


class Sprint4CrmOpportunityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        tenant_auth.DATA_DIR = Path(self.temp.name)
        tenant_auth.DB_PATH = tenant_auth.DATA_DIR / 'madmallard.sqlite3'

    def tearDown(self):
        self.temp.cleanup()

    def test_opportunity_crud_and_pipeline_order(self):
        company = crm_companies.create_company('solutions', name='Acme')
        contact = crm_contacts.create_contact(
            'solutions', name='Jane', company_id=company.id
        )
        later = crm_opportunities.create_opportunity(
            'solutions',
            title='Later deal',
            company_id=company.id,
            contact_id=contact.id,
            stage='proposal',
            value_cents=250000,
            expected_close_date='2026-12-31',
            position=2,
        )
        earlier = crm_opportunities.create_opportunity(
            'solutions',
            title='Earlier deal',
            company_id=company.id,
            contact_id=contact.id,
            stage='proposal',
            value_cents=100000,
            position=1,
        )
        self.assertEqual(
            [earlier.id, later.id],
            [o.id for o in crm_opportunities.list_opportunities(
                'solutions', stage='proposal'
            )],
        )
        updated = crm_opportunities.update_opportunity(
            'solutions', later.id, stage='negotiation', value_cents=300000
        )
        self.assertEqual('negotiation', updated.stage)
        self.assertEqual(300000, updated.value_cents)
        self.assertEqual('Acme', updated.company_name)
        self.assertEqual('Jane', updated.contact_name)

    def test_foreign_relationships_are_rejected(self):
        foreign_company = crm_companies.create_company('adventures', name='Foreign')
        foreign_contact = crm_contacts.create_contact(
            'adventures', name='Traveler', company_id=foreign_company.id
        )
        with self.assertRaises(ValueError):
            crm_opportunities.create_opportunity(
                'solutions', title='Bad company', company_id=foreign_company.id
            )
        with self.assertRaises(ValueError):
            crm_opportunities.create_opportunity(
                'solutions', title='Bad contact', contact_id=foreign_contact.id
            )

    def test_contact_company_mismatch_is_rejected(self):
        first = crm_companies.create_company('solutions', name='First')
        second = crm_companies.create_company('solutions', name='Second')
        contact = crm_contacts.create_contact(
            'solutions', name='Bound Contact', company_id=first.id
        )
        with self.assertRaisesRegex(ValueError, 'does not match'):
            crm_opportunities.create_opportunity(
                'solutions', title='Mismatch', company_id=second.id,
                contact_id=contact.id
            )

    def test_unattached_contact_can_be_paired_with_company(self):
        company = crm_companies.create_company('solutions', name='Acme')
        contact = crm_contacts.create_contact('solutions', name='Unattached')
        opportunity = crm_opportunities.create_opportunity(
            'solutions', title='Valid', company_id=company.id, contact_id=contact.id
        )
        self.assertEqual(company.id, opportunity.company_id)
        self.assertEqual(contact.id, opportunity.contact_id)

    def test_filters_cannot_probe_foreign_records(self):
        foreign_company = crm_companies.create_company('adventures', name='Foreign')
        foreign_contact = crm_contacts.create_contact('adventures', name='Foreign Contact')
        with self.assertRaises(ValueError):
            crm_opportunities.list_opportunities(
                'solutions', company_id=foreign_company.id
            )
        with self.assertRaises(ValueError):
            crm_opportunities.list_opportunities(
                'solutions', contact_id=foreign_contact.id
            )

    def test_archived_opportunity_hidden_and_immutable(self):
        opportunity = crm_opportunities.create_opportunity(
            'solutions', title='Old deal'
        )
        archived = crm_opportunities.archive_opportunity(
            'solutions', opportunity.id
        )
        self.assertEqual('archived', archived.status)
        self.assertEqual([], crm_opportunities.list_opportunities('solutions'))
        self.assertEqual(
            [opportunity.id],
            [o.id for o in crm_opportunities.list_opportunities(
                'solutions', include_archived=True
            )],
        )
        with self.assertRaises(ValueError):
            crm_opportunities.update_opportunity(
                'solutions', opportunity.id, title='No'
            )

    def test_validation_rejects_invalid_pipeline_metadata(self):
        cases = (
            {'title': ''},
            {'title': 'Bad stage', 'stage': 'deleted'},
            {'title': 'Bad value', 'value_cents': -1},
            {'title': 'Bad currency', 'currency': 'US'},
            {'title': 'Bad date', 'expected_close_date': '12/31/2026'},
            {'title': 'Bad position', 'position': -1},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    crm_opportunities.create_opportunity('solutions', **kwargs)

    def test_inactive_tenant_cannot_use_opportunities(self):
        crm_opportunities.create_opportunity('solutions', title='Before suspension')
        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_organizations SET status='suspended' WHERE slug='solutions'"
            )
            conn.commit()
        with self.assertRaises(ValueError):
            crm_opportunities.list_opportunities('solutions')
        with self.assertRaises(ValueError):
            crm_opportunities.create_opportunity('solutions', title='Blocked')


if __name__ == '__main__':
    unittest.main()
