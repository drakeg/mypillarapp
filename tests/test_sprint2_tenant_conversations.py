from __future__ import annotations

import importlib
from pathlib import Path
import sys
import tempfile
import unittest

SITE_DIR = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SITE_DIR) not in sys.path:
    sys.path.insert(0, str(SITE_DIR))

import messaging
import tenant_conversations


class Sprint2TenantConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        messaging.DATA_DIR = data_dir
        messaging.DB_PATH = data_dir / 'madmallard.sqlite3'
        importlib.reload(tenant_conversations)

    def tearDown(self):
        self.temp_dir.cleanup()

    def create(self, tenant: str, email: str = 'shared@example.com'):
        return tenant_conversations.create_conversation(
            tenant_slug=tenant,
            kind='chat',
            name='Test Customer',
            email=email,
            body=f'Message for {tenant}',
            subject='Tenant test',
        )

    def test_existing_rows_migrate_to_solutions_tenant(self):
        legacy = messaging.create_conversation(
            kind='chat',
            name='Legacy Customer',
            email='legacy@example.com',
            body='Legacy message',
        )

        tenant_conversations.ensure_schema()

        row = tenant_conversations.get_conversation('solutions', legacy['token'])
        self.assertIsNotNone(row)
        self.assertEqual(row['organization_slug'], 'solutions')

    def test_same_email_is_isolated_between_tenants(self):
        solutions = self.create('solutions')
        adventures = self.create('adventures')

        solution_rows = tenant_conversations.list_customer_conversations(
            'solutions', 'shared@example.com'
        )
        adventure_rows = tenant_conversations.list_customer_conversations(
            'adventures', 'shared@example.com'
        )

        self.assertEqual([row['token'] for row in solution_rows], [solutions['token']])
        self.assertEqual([row['token'] for row in adventure_rows], [adventures['token']])

    def test_cross_tenant_token_lookup_returns_none(self):
        conversation = self.create('solutions')

        self.assertIsNone(
            tenant_conversations.get_conversation('adventures', conversation['token'])
        )

    def test_cross_tenant_message_write_is_rejected(self):
        conversation = self.create('solutions')

        result = tenant_conversations.add_message(
            'adventures',
            conversation['token'],
            body='Should not be written',
        )

        self.assertIsNone(result)
        with messaging.db() as conn:
            count = conn.execute(
                'SELECT COUNT(*) AS count FROM messages WHERE conversation_id = ?',
                (conversation['id'],),
            ).fetchone()['count']
        self.assertEqual(count, 1)

    def test_matching_tenant_message_write_succeeds(self):
        conversation = self.create('solutions')

        result = tenant_conversations.add_message(
            'solutions',
            conversation['token'],
            body='Allowed reply',
        )

        self.assertIsNotNone(result)
        with messaging.db() as conn:
            count = conn.execute(
                'SELECT COUNT(*) AS count FROM messages WHERE conversation_id = ?',
                (conversation['id'],),
            ).fetchone()['count']
        self.assertEqual(count, 2)

    def test_cross_tenant_update_is_rejected(self):
        conversation = self.create('solutions')

        updated = tenant_conversations.update_conversation(
            'adventures', conversation['token'], status='closed'
        )

        self.assertFalse(updated)
        current = tenant_conversations.get_conversation('solutions', conversation['token'])
        self.assertEqual(current['status'], 'new')


if __name__ == '__main__':
    unittest.main()
