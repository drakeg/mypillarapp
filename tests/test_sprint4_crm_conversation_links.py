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
import crm_conversation_links
import crm_opportunities
import messaging
import tenant_auth
import tenant_conversations


class Sprint4ConversationLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        data = Path(self.temp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        messaging.DATA_DIR = data
        messaging.DB_PATH = data / 'madmallard.sqlite3'

    def tearDown(self):
        self.temp.cleanup()

    def make_conversation(self, tenant='solutions', kind='project_request'):
        return tenant_conversations.create_conversation(
            tenant_slug=tenant, kind=kind, name='Jane', email='jane@example.com',
            body='Need help', company='Acme', subject='Project'
        )

    def test_link_preserves_conversation_and_records_reference(self):
        conversation = self.make_conversation()
        company = crm_companies.create_company('solutions', name='Acme')
        contact = crm_contacts.create_contact(
            'solutions', name='Jane', company_id=company.id
        )
        opportunity = crm_opportunities.create_opportunity(
            'solutions', title='Project', company_id=company.id, contact_id=contact.id
        )
        link = crm_conversation_links.link_conversation(
            'solutions', conversation['token'],
            company_id=company.id, contact_id=contact.id, opportunity_id=opportunity.id
        )
        self.assertEqual('project_request', link.conversation_kind)
        self.assertEqual(conversation['token'], link.conversation_token)
        still_there = tenant_conversations.get_conversation(
            'solutions', conversation['token']
        )
        self.assertEqual('Need help', messaging.get_conversation(conversation['token'])[1][0]['body'])
        self.assertEqual(conversation['id'], still_there['id'])

    def test_link_is_idempotent_update_not_duplicate(self):
        conversation = self.make_conversation(kind='chat')
        first = crm_conversation_links.link_conversation(
            'solutions', conversation['token']
        )
        company = crm_companies.create_company('solutions', name='Acme')
        second = crm_conversation_links.link_conversation(
            'solutions', conversation['token'], company_id=company.id
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(company.id, second.company_id)
        self.assertEqual(1, len(crm_conversation_links.list_links('solutions')))

    def test_foreign_conversation_and_crm_links_fail_closed(self):
        foreign_conversation = self.make_conversation(tenant='adventures')
        foreign_company = crm_companies.create_company('adventures', name='Foreign')
        with self.assertRaises(ValueError):
            crm_conversation_links.link_conversation(
                'solutions', foreign_conversation['token']
            )
        local = self.make_conversation()
        with self.assertRaises(ValueError):
            crm_conversation_links.link_conversation(
                'solutions', local['token'], company_id=foreign_company.id
            )

    def test_inconsistent_crm_relationships_are_rejected(self):
        conversation = self.make_conversation()
        first = crm_companies.create_company('solutions', name='First')
        second = crm_companies.create_company('solutions', name='Second')
        contact = crm_contacts.create_contact(
            'solutions', name='Jane', company_id=first.id
        )
        with self.assertRaises(ValueError):
            crm_conversation_links.link_conversation(
                'solutions', conversation['token'],
                company_id=second.id, contact_id=contact.id
            )

    def test_filters_are_tenant_safe_and_unlink_does_not_delete_conversation(self):
        conversation = self.make_conversation()
        company = crm_companies.create_company('solutions', name='Acme')
        crm_conversation_links.link_conversation(
            'solutions', conversation['token'], company_id=company.id
        )
        self.assertEqual(
            [conversation['token']],
            [l.conversation_token for l in crm_conversation_links.list_links(
                'solutions', company_id=company.id
            )],
        )
        self.assertTrue(
            crm_conversation_links.unlink_conversation(
                'solutions', conversation['token']
            )
        )
        self.assertIsNotNone(
            tenant_conversations.get_conversation('solutions', conversation['token'])
        )
        self.assertIsNone(
            crm_conversation_links.get_link('solutions', conversation['token'])
        )

    def test_suspended_tenant_cannot_manage_links(self):
        conversation = self.make_conversation()
        crm_conversation_links.link_conversation(
            'solutions', conversation['token']
        )
        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_organizations SET status='suspended' WHERE slug='solutions'"
            )
            conn.commit()
        with self.assertRaises(ValueError):
            crm_conversation_links.list_links('solutions')


if __name__ == '__main__':
    unittest.main()
