from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import ai_boundary
import ai_execution
import ai_settings
import ai_summarization
import portal_projects
import tenant_auth
import tenant_conversations
import tenant_sites


class FakeProvider:
    provider_name = 'fake-provider'
    model_id = 'fake-summary-model'

    def __init__(self):
        self.calls = []

    def generate(self, prompt, *, max_output_units, timeout_seconds):
        self.calls.append(prompt)
        return ai_execution.ProviderResult(
            text='Non-authoritative summary',
            input_units=max(1, (len(prompt) + 3) // 4),
            output_units=25,
        )


class Sprint7AISummarizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        import messaging
        messaging.DATA_DIR = data
        messaging.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()
        self.owner = self._user('solutions', 'owner@example.com', 'owner')
        self.staff = self._user('solutions', 'staff@example.com', 'staff')
        self.customer_a = self._user('solutions', 'a@example.com', 'viewer')
        self.customer_b = self._user('solutions', 'b@example.com', 'viewer')
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

    def _user(self, organization_slug, email, role):
        with tenant_auth.db() as conn:
            org = conn.execute(
                'SELECT id FROM auth_organizations WHERE slug=?',
                (organization_slug,),
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

    def test_summary_is_non_authoritative_and_returns_sources(self):
        project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.customer_a,
            title='Migration',
            summary='Move workloads',
        )
        provider = FakeProvider()
        result = ai_summarization.summarize_records(
            self.staff,
            'solutions',
            references=(
                ai_boundary.AIContextReference(
                    'portal_project', str(project.id)
                ),
            ),
            provider=provider,
        )
        self.assertEqual('Non-authoritative summary', result.text)
        self.assertFalse(result.authoritative)
        self.assertEqual(1, len(result.source_references))
        self.assertEqual(
            ai_boundary.OUTPUT_CLASSIFICATION,
            result.output_classification,
        )

    def test_internal_and_customer_message_visibility_labels_are_preserved(self):
        conversation = tenant_conversations.create_conversation(
            tenant_slug='solutions',
            kind='chat',
            name='Customer',
            email='a@example.com',
            body='Customer-visible opening',
            subject='Help',
        )
        tenant_conversations.add_message(
            'solutions',
            conversation['token'],
            body='Internal staff note',
            sender='Staff',
            sender_type='admin',
            internal=True,
        )
        provider = FakeProvider()
        ai_summarization.summarize_records(
            self.staff,
            'solutions',
            references=(
                ai_boundary.AIContextReference(
                    'conversation', conversation['token']
                ),
            ),
            provider=provider,
        )
        prompt = provider.calls[0]
        self.assertIn('[customer]', prompt)
        self.assertIn('[internal]', prompt)
        self.assertIn('Internal staff note', prompt)

    def test_multiple_portal_customers_fail_before_provider_call(self):
        one = portal_projects.create_project(
            'solutions',
            customer_user_id=self.customer_a,
            title='A',
        )
        two = portal_projects.create_project(
            'solutions',
            customer_user_id=self.customer_b,
            title='B',
        )
        provider = FakeProvider()
        with self.assertRaises(PermissionError):
            ai_summarization.summarize_records(
                self.staff,
                'solutions',
                references=(
                    ai_boundary.AIContextReference(
                        'portal_project', str(one.id)
                    ),
                    ai_boundary.AIContextReference(
                        'portal_project', str(two.id)
                    ),
                ),
                provider=provider,
            )
        self.assertEqual([], provider.calls)

    def test_multiple_conversation_customers_fail_before_provider_call(self):
        one = tenant_conversations.create_conversation(
            tenant_slug='solutions',
            kind='chat',
            name='A',
            email='a@example.com',
            body='A',
        )
        two = tenant_conversations.create_conversation(
            tenant_slug='solutions',
            kind='chat',
            name='B',
            email='b@example.com',
            body='B',
        )
        provider = FakeProvider()
        with self.assertRaises(PermissionError):
            ai_summarization.summarize_records(
                self.staff,
                'solutions',
                references=(
                    ai_boundary.AIContextReference(
                        'conversation', one['token']
                    ),
                    ai_boundary.AIContextReference(
                        'conversation', two['token']
                    ),
                ),
                provider=provider,
            )
        self.assertEqual([], provider.calls)

    def test_summary_does_not_persist_generated_text(self):
        project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.customer_a,
            title='Keep',
            summary='Canonical summary',
        )
        provider = FakeProvider()
        ai_summarization.summarize_records(
            self.staff,
            'solutions',
            references=(
                ai_boundary.AIContextReference(
                    'portal_project', str(project.id)
                ),
            ),
            provider=provider,
        )
        after = portal_projects.get_project('solutions', project.id)
        self.assertEqual('Canonical summary', after.summary)


if __name__ == '__main__':
    unittest.main()
