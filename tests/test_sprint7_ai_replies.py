from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import ai_execution
import ai_replies
import ai_settings
import messaging
import portal_messaging
import portal_projects
import tenant_auth
import tenant_conversations
import tenant_sites


class FakeProvider:
    provider_name = 'fake-provider'
    model_id = 'fake-reply-model'

    def __init__(self):
        self.calls = []

    def generate(self, prompt, *, max_output_units, timeout_seconds):
        self.calls.append(prompt)
        return ai_execution.ProviderResult(
            text='Suggested customer reply',
            input_units=max(1, (len(prompt) + 3) // 4),
            output_units=35,
        )


class Sprint7AIReplySuggestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        messaging.DATA_DIR = data
        messaging.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

        self.owner = self._user('owner@example.com', 'owner')
        self.staff = self._user('staff@example.com', 'staff')
        self.viewer = self._user('viewer@example.com', 'viewer')
        self.customer = self._user('customer@example.com', 'viewer')
        ai_settings.update_settings(
            self.owner,
            'solutions',
            enabled=True,
            max_input_units=6000,
            max_output_units=1000,
            rolling_limit_units=30000,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _user(self, email, role):
        with tenant_auth.db() as conn:
            org = conn.execute(
                "SELECT id FROM auth_organizations WHERE slug='solutions'"
            ).fetchone()
            role_row = conn.execute(
                'SELECT id FROM auth_roles WHERE slug=?',
                (role,),
            ).fetchone()
            now = tenant_auth.now()
            cur = conn.execute(
                '''INSERT INTO auth_users(
                       created_at,updated_at,organization_id,email,
                       first_name,last_name,password_hash,role,is_active
                   ) VALUES(?,?,?,?,?,?,?,?,1)''',
                (
                    now, now, org['id'], email, 'AI', 'User',
                    tenant_auth.hash_password('abcdefghijkl'), role,
                ),
            )
            user_id = int(cur.lastrowid)
            conn.execute(
                '''INSERT INTO auth_memberships(
                       created_at,updated_at,user_id,organization_id,
                       role_id,status
                   ) VALUES(?,?,?,?,?,'active')''',
                (now, now, user_id, org['id'], role_row['id']),
            )
            conn.commit()
        return user_id

    def _conversation(self):
        return tenant_conversations.create_conversation(
            tenant_slug='solutions',
            kind='chat',
            name='Customer',
            email='customer@example.com',
            body='Can you give me an update?',
            subject='Project status',
        )

    def test_reply_uses_only_customer_visible_messages_and_does_not_send(self):
        conversation = self._conversation()
        tenant_conversations.add_message(
            'solutions',
            conversation['token'],
            body='Do not reveal this internal note.',
            sender='Staff',
            sender_type='admin',
            internal=True,
        )
        tenant_conversations.add_message(
            'solutions',
            conversation['token'],
            body='We are reviewing it.',
            sender='Staff',
            sender_type='admin',
            internal=False,
        )
        before, before_messages = messaging.get_conversation(
            conversation['token']
        )
        provider = FakeProvider()

        result = ai_replies.suggest_reply(
            self.staff,
            'solutions',
            conversation_token=conversation['token'],
            provider=provider,
        )

        self.assertEqual('Suggested customer reply', result.text)
        self.assertTrue(result.send_required)
        self.assertEqual(1, len(provider.calls))
        self.assertIn('Can you give me an update?', provider.calls[0])
        self.assertIn('We are reviewing it.', provider.calls[0])
        self.assertNotIn('Do not reveal this internal note.', provider.calls[0])

        after, after_messages = messaging.get_conversation(
            conversation['token']
        )
        self.assertEqual(dict(before), dict(after))
        self.assertEqual(
            [dict(row) for row in before_messages],
            [dict(row) for row in after_messages],
        )

    def test_viewer_cannot_generate_customer_reply(self):
        conversation = self._conversation()
        provider = FakeProvider()
        with self.assertRaises(PermissionError):
            ai_replies.suggest_reply(
                self.viewer,
                'solutions',
                conversation_token=conversation['token'],
                provider=provider,
            )
        self.assertEqual([], provider.calls)

    def test_linked_project_must_match_conversation_customer(self):
        conversation = self._conversation()
        project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.customer,
            title='Migration Project',
            summary='Cloud migration is underway.',
        )
        portal_messaging.link_conversation(
            'solutions',
            conversation['token'],
            customer_user_id=self.customer,
            project_id=project.id,
        )
        provider = FakeProvider()
        result = ai_replies.suggest_reply(
            self.staff,
            'solutions',
            conversation_token=conversation['token'],
            project_id=project.id,
            provider=provider,
        )
        self.assertEqual(project.id, result.project_id)
        self.assertIn('Migration Project', provider.calls[0])

    def test_unlinked_project_is_rejected_before_provider_call(self):
        conversation = self._conversation()
        project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.customer,
            title='Unlinked Project',
        )
        provider = FakeProvider()
        with self.assertRaises(PermissionError):
            ai_replies.suggest_reply(
                self.staff,
                'solutions',
                conversation_token=conversation['token'],
                project_id=project.id,
                provider=provider,
            )
        self.assertEqual([], provider.calls)

    def test_disabled_ai_does_not_call_provider_or_change_conversation(self):
        conversation = self._conversation()
        ai_settings.update_settings(
            self.owner,
            'solutions',
            enabled=False,
        )
        provider = FakeProvider()
        with self.assertRaises(PermissionError):
            ai_replies.suggest_reply(
                self.staff,
                'solutions',
                conversation_token=conversation['token'],
                provider=provider,
            )
        self.assertEqual([], provider.calls)
        current = tenant_conversations.get_conversation(
            'solutions', conversation['token']
        )
        self.assertEqual('new', current['status'])


if __name__ == '__main__':
    unittest.main()
