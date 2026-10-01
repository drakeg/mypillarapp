from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import crm_activities
import crm_companies
import crm_contacts
import crm_opportunities
import crm_tasks
import tenant_auth


class Sprint4CrmActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        tenant_auth.DATA_DIR = Path(self.temp.name)
        tenant_auth.DB_PATH = tenant_auth.DATA_DIR / 'madmallard.sqlite3'

    def tearDown(self):
        self.temp.cleanup()

    def test_append_and_timeline_filters(self):
        company = crm_companies.create_company('solutions', name='Acme')
        contact = crm_contacts.create_contact('solutions', name='Jane', company_id=company.id)
        opp = crm_opportunities.create_opportunity('solutions', title='Deal', company_id=company.id, contact_id=contact.id)
        task = crm_tasks.create_task('solutions', title='Call', opportunity_id=opp.id)
        a1 = crm_activities.add_activity('solutions', actor='greg', body='First note', company_id=company.id)
        a2 = crm_activities.add_activity('solutions', actor='greg', body='Called Jane', kind='call', contact_id=contact.id, opportunity_id=opp.id, task_id=task.id)
        self.assertEqual([a2.id, a1.id], [a.id for a in crm_activities.list_activities('solutions')])
        self.assertEqual([a2.id], [a.id for a in crm_activities.list_activities('solutions', kind='call')])
        self.assertEqual([a2.id], [a.id for a in crm_activities.list_activities('solutions', task_id=task.id)])

    def test_foreign_links_and_filters_fail_closed(self):
        company = crm_companies.create_company('adventures', name='Foreign')
        with self.assertRaises(ValueError):
            crm_activities.add_activity('solutions', actor='greg', body='blocked', company_id=company.id)
        with self.assertRaises(ValueError):
            crm_activities.list_activities('solutions', company_id=company.id)

    def test_append_only_api_has_no_update_or_delete(self):
        self.assertFalse(hasattr(crm_activities, 'update_activity'))
        self.assertFalse(hasattr(crm_activities, 'delete_activity'))

    def test_validation(self):
        for kwargs in (
            {'actor':'', 'body':'note'},
            {'actor':'greg', 'body':''},
            {'actor':'greg', 'body':'note', 'kind':'unknown'},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    crm_activities.add_activity('solutions', **kwargs)
        with self.assertRaises(ValueError):
            crm_activities.list_activities('solutions', limit=0)

    def test_tenant_isolation_and_suspension(self):
        crm_activities.add_activity('solutions', actor='greg', body='Solutions note')
        crm_activities.add_activity('adventures', actor='greg', body='Adventures note')
        self.assertEqual(['Solutions note'], [a.body for a in crm_activities.list_activities('solutions')])
        with tenant_auth.db() as conn:
            conn.execute("UPDATE auth_organizations SET status='suspended' WHERE slug='solutions'")
            conn.commit()
        with self.assertRaises(ValueError):
            crm_activities.list_activities('solutions')


if __name__ == '__main__':
    unittest.main()
