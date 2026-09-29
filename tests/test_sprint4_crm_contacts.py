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
import tenant_auth


class Sprint4CrmContactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        tenant_auth.DATA_DIR = Path(self.temp.name)
        tenant_auth.DB_PATH = tenant_auth.DATA_DIR / 'madmallard.sqlite3'

    def tearDown(self):
        self.temp.cleanup()

    def test_contact_crud_and_normalization_are_tenant_scoped(self):
        company = crm_companies.create_company('solutions', name='Acme')
        contact = crm_contacts.create_contact(
            'solutions',
            name=' Jane Smith ',
            email=' JANE@EXAMPLE.COM ',
            phone='+1 (814) 555-1212',
            title='CTO',
            company_id=company.id,
        )
        self.assertEqual('Jane Smith', contact.name)
        self.assertEqual('jane@example.com', contact.email)
        self.assertEqual('+18145551212', contact.phone)
        self.assertEqual('Acme', contact.company_name)
        self.assertIsNone(crm_contacts.get_contact('adventures', contact.id))

        updated = crm_contacts.update_contact(
            'solutions', contact.id, status='customer', title='VP Engineering'
        )
        self.assertEqual('customer', updated.status)
        self.assertEqual('VP Engineering', updated.title)

    def test_contact_cannot_link_to_foreign_company(self):
        foreign = crm_companies.create_company('adventures', name='Foreign Co')
        with self.assertRaises(ValueError):
            crm_contacts.create_contact(
                'solutions', name='Wrong Link', company_id=foreign.id
            )

        local = crm_contacts.create_contact('solutions', name='Local')
        with self.assertRaises(ValueError):
            crm_contacts.update_contact(
                'solutions', local.id, company_id=foreign.id
            )

    def test_company_link_can_be_removed(self):
        company = crm_companies.create_company('solutions', name='Detach Co')
        contact = crm_contacts.create_contact(
            'solutions', name='Detach Me', company_id=company.id
        )
        detached = crm_contacts.update_contact(
            'solutions', contact.id, company_id=None
        )
        self.assertIsNone(detached.company_id)
        self.assertEqual('', detached.company_name)

    def test_archived_contact_hidden_and_immutable(self):
        contact = crm_contacts.create_contact('solutions', name='Old Contact')
        archived = crm_contacts.archive_contact('solutions', contact.id)
        self.assertEqual('archived', archived.status)
        self.assertEqual([], crm_contacts.list_contacts('solutions'))
        self.assertEqual(
            [contact.id],
            [c.id for c in crm_contacts.list_contacts('solutions', include_archived=True)],
        )
        with self.assertRaises(ValueError):
            crm_contacts.update_contact('solutions', contact.id, notes='blocked')

    def test_validation_rejects_bad_email_phone_name_and_status(self):
        with self.assertRaises(ValueError):
            crm_contacts.create_contact('solutions', name='')
        with self.assertRaises(ValueError):
            crm_contacts.create_contact(
                'solutions', name='Bad Email', email='not-an-email'
            )
        with self.assertRaises(ValueError):
            crm_contacts.create_contact(
                'solutions', name='Bad Phone', phone='123'
            )
        with self.assertRaises(ValueError):
            crm_contacts.create_contact(
                'solutions', name='Bad Status', status='deleted'
            )

    def test_search_and_company_filter_are_scoped(self):
        local = crm_companies.create_company('solutions', name='Local Cloud')
        other = crm_companies.create_company('solutions', name='Other Co')
        crm_contacts.create_contact(
            'solutions', name='Alice Percent %', email='alice@example.com',
            company_id=local.id, title='Engineer'
        )
        crm_contacts.create_contact(
            'solutions', name='Bob', email='bob@example.com', company_id=other.id
        )
        crm_contacts.create_contact(
            'adventures', name='Alice Travel', email='alice@travel.example'
        )
        self.assertEqual(
            ['Alice Percent %'],
            [c.name for c in crm_contacts.list_contacts('solutions', query='Alice')],
        )
        self.assertEqual(
            ['Alice Percent %'],
            [c.name for c in crm_contacts.list_contacts('solutions', company_id=local.id)],
        )
        self.assertEqual(
            ['Alice Percent %'],
            [c.name for c in crm_contacts.list_contacts('solutions', query='%')],
        )

    def test_foreign_tenant_company_filter_is_rejected(self):
        foreign = crm_companies.create_company('adventures', name='Foreign')
        with self.assertRaises(ValueError):
            crm_contacts.list_contacts('solutions', company_id=foreign.id)

    def test_inactive_tenant_cannot_use_contacts(self):
        crm_contacts.create_contact('solutions', name='Before suspension')
        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_organizations SET status='suspended' WHERE slug='solutions'"
            )
            conn.commit()
        with self.assertRaises(ValueError):
            crm_contacts.list_contacts('solutions')
        with self.assertRaises(ValueError):
            crm_contacts.create_contact('solutions', name='Blocked')


if __name__ == '__main__':
    unittest.main()
