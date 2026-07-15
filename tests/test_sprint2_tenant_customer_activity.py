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
import tenant_auth
import tenant_conversations


class Sprint2TenantCustomerActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        db_path = data_dir / 'madmallard.sqlite3'
        messaging.DATA_DIR = data_dir
        messaging.DB_PATH = db_path
        tenant_auth.DATA_DIR = data_dir
        tenant_auth.DB_PATH = db_path
        importlib.reload(tenant_conversations)
        self.solutions_user = {
            'email': 'shared@example.com',
            'organization_slug': 'solutions',
        }
        self.adventures_user = {
            'email': 'shared@example.com',
            'organization_slug': 'adventures',
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def create(self, tenant: str, kind: str = 'chat'):
        return tenant_conversations.create_conversation(
            tenant_slug=tenant,
            kind=kind,
            name='Shared Customer',
            email='shared@example.com',
            body=f'{tenant} {kind}',
            subject=f'{tenant} subject',
        )

    def test_customer_history_is_tenant_scoped(self):
        solutions = self.create('solutions')
        self.create('adventures')

        rows = tenant_auth._customer_history(self.solutions_user, 'chat')

        self.assertEqual([row['token'] for row in rows], [solutions['token']])

    def test_customer_conversation_rejects_cross_tenant_token(self):
        adventures = self.create('adventures')

        conversation, messages = tenant_auth._customer_conversation(
            self.solutions_user, adventures['token']
        )

        self.assertIsNone(conversation)
        self.assertEqual(messages, [])

    def test_customer_conversation_accepts_matching_tenant_and_email(self):
        solutions = self.create('solutions')

        conversation, messages = tenant_auth._customer_conversation(
            self.solutions_user, solutions['token']
        )

        self.assertEqual(conversation['token'], solutions['token'])
        self.assertEqual(len(messages), 1)

    def test_customer_activity_counts_only_current_tenant(self):
        self.create('solutions', 'chat')
        self.create('solutions', 'project_request')
        self.create('adventures', 'chat')

        counts, recent = tenant_auth._customer_activity(self.solutions_user)

        self.assertEqual(counts['total'], 2)
        self.assertEqual(counts['conversations'], 1)
        self.assertEqual(counts['requests'], 1)
        self.assertEqual(len(recent), 2)

    def test_same_email_has_independent_activity_per_tenant(self):
        self.create('solutions', 'project_request')
        adventure = self.create('adventures', 'chat')

        counts, recent = tenant_auth._customer_activity(self.adventures_user)

        self.assertEqual(counts['total'], 1)
        self.assertEqual(counts['conversations'], 1)
        self.assertEqual([row['token'] for row in recent], [adventure['token']])


if __name__ == '__main__':
    unittest.main()
