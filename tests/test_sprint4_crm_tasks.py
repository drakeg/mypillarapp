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
import crm_tasks
import tenant_auth


class Sprint4CrmTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        tenant_auth.DATA_DIR = Path(self.temp.name)
        tenant_auth.DB_PATH = tenant_auth.DATA_DIR / 'madmallard.sqlite3'

    def tearDown(self):
        self.temp.cleanup()

    def test_task_crud_due_order_and_relationship_labels(self):
        company = crm_companies.create_company('solutions', name='Acme')
        contact = crm_contacts.create_contact(
            'solutions', name='Jane', company_id=company.id
        )
        opportunity = crm_opportunities.create_opportunity(
            'solutions', title='Cloud migration',
            company_id=company.id, contact_id=contact.id
        )
        later = crm_tasks.create_task(
            'solutions', title='Send proposal', company_id=company.id,
            contact_id=contact.id, opportunity_id=opportunity.id,
            priority='high', due_date='2026-11-15'
        )
        earlier = crm_tasks.create_task(
            'solutions', title='Call client', opportunity_id=opportunity.id,
            due_date='2026-11-01'
        )
        undated = crm_tasks.create_task('solutions', title='Research')
        self.assertEqual(
            [earlier.id, later.id, undated.id],
            [t.id for t in crm_tasks.list_tasks('solutions')],
        )
        updated = crm_tasks.update_task(
            'solutions', later.id, status='in_progress', priority='urgent'
        )
        self.assertEqual('in_progress', updated.status)
        self.assertEqual('urgent', updated.priority)
        self.assertEqual('Acme', updated.company_name)
        self.assertEqual('Jane', updated.contact_name)
        self.assertEqual('Cloud migration', updated.opportunity_title)

    def test_foreign_relationships_are_rejected(self):
        company = crm_companies.create_company('adventures', name='Foreign')
        contact = crm_contacts.create_contact(
            'adventures', name='Traveler', company_id=company.id
        )
        opportunity = crm_opportunities.create_opportunity(
            'adventures', title='Foreign opportunity',
            company_id=company.id, contact_id=contact.id
        )
        for kwargs in (
            {'company_id': company.id},
            {'contact_id': contact.id},
            {'opportunity_id': opportunity.id},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    crm_tasks.create_task('solutions', title='Blocked', **kwargs)

    def test_contact_company_mismatch_is_rejected(self):
        first = crm_companies.create_company('solutions', name='First')
        second = crm_companies.create_company('solutions', name='Second')
        contact = crm_contacts.create_contact(
            'solutions', name='Bound contact', company_id=first.id
        )
        with self.assertRaisesRegex(ValueError, 'contact company'):
            crm_tasks.create_task(
                'solutions', title='Mismatch',
                company_id=second.id, contact_id=contact.id
            )

    def test_opportunity_relationship_mismatch_is_rejected(self):
        first = crm_companies.create_company('solutions', name='First')
        second = crm_companies.create_company('solutions', name='Second')
        first_contact = crm_contacts.create_contact(
            'solutions', name='First contact', company_id=first.id
        )
        second_contact = crm_contacts.create_contact(
            'solutions', name='Second contact', company_id=second.id
        )
        opportunity = crm_opportunities.create_opportunity(
            'solutions', title='Bound opportunity',
            company_id=first.id, contact_id=first_contact.id
        )
        with self.assertRaisesRegex(ValueError, 'opportunity company'):
            crm_tasks.create_task(
                'solutions', title='Wrong company',
                company_id=second.id, opportunity_id=opportunity.id
            )
        with self.assertRaisesRegex(ValueError, 'opportunity contact'):
            crm_tasks.create_task(
                'solutions', title='Wrong contact',
                contact_id=second_contact.id, opportunity_id=opportunity.id
            )

    def test_relationship_filters_cannot_probe_foreign_records(self):
        company = crm_companies.create_company('adventures', name='Foreign')
        contact = crm_contacts.create_contact('adventures', name='Foreign contact')
        opportunity = crm_opportunities.create_opportunity(
            'adventures', title='Foreign opportunity'
        )
        for kwargs in (
            {'company_id': company.id},
            {'contact_id': contact.id},
            {'opportunity_id': opportunity.id},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    crm_tasks.list_tasks('solutions', **kwargs)

    def test_task_validation(self):
        cases = (
            {'title': ''},
            {'title': 'Bad status', 'status': 'deleted'},
            {'title': 'Bad priority', 'priority': 'critical'},
            {'title': 'Bad date', 'due_date': '11/01/2026'},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    crm_tasks.create_task('solutions', **kwargs)

    def test_status_priority_and_relationship_filters(self):
        company = crm_companies.create_company('solutions', name='Acme')
        contact = crm_contacts.create_contact('solutions', name='Jane')
        opportunity = crm_opportunities.create_opportunity(
            'solutions', title='Opportunity'
        )
        wanted = crm_tasks.create_task(
            'solutions', title='Wanted', company_id=company.id,
            contact_id=contact.id, opportunity_id=opportunity.id,
            status='open', priority='urgent'
        )
        crm_tasks.create_task(
            'solutions', title='Other', status='done', priority='low'
        )
        self.assertEqual(
            [wanted.id],
            [t.id for t in crm_tasks.list_tasks(
                'solutions', status='open', priority='urgent',
                company_id=company.id, contact_id=contact.id,
                opportunity_id=opportunity.id
            )],
        )

    def test_archived_task_hidden_and_immutable(self):
        task = crm_tasks.create_task('solutions', title='Old task')
        archived = crm_tasks.archive_task('solutions', task.id)
        self.assertEqual('archived', archived.status)
        self.assertEqual([], crm_tasks.list_tasks('solutions'))
        self.assertEqual(
            [task.id],
            [t.id for t in crm_tasks.list_tasks(
                'solutions', include_archived=True
            )],
        )
        with self.assertRaises(ValueError):
            crm_tasks.update_task('solutions', task.id, title='Blocked')

    def test_inactive_tenant_cannot_use_tasks(self):
        crm_tasks.create_task('solutions', title='Before suspension')
        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_organizations SET status='suspended' WHERE slug='solutions'"
            )
            conn.commit()
        with self.assertRaises(ValueError):
            crm_tasks.list_tasks('solutions')
        with self.assertRaises(ValueError):
            crm_tasks.create_task('solutions', title='Blocked')


if __name__ == '__main__':
    unittest.main()
