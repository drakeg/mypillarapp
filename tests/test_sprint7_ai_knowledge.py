from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import ai_execution
import ai_knowledge
import ai_settings
import crm_companies
import messaging
import site_pages
import tenant_auth
import tenant_conversations
import tenant_sites


class FakeProvider:
    provider_name = 'fake-provider'
    model_id = 'fake-knowledge-model'

    def __init__(self):
        self.calls = []

    def generate(self, prompt, *, max_output_units, timeout_seconds):
        self.calls.append(prompt)
        return ai_execution.ProviderResult(
            text='Answer from retrieved tenant records',
            input_units=max(1, (len(prompt) + 3) // 4),
            output_units=40,
        )


class Sprint7AIKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        messaging.DATA_DIR = data
        messaging.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

        self.owner = self._user('solutions', 'owner@example.com', 'owner')
        self.staff = self._user('solutions', 'staff@example.com', 'staff')
        self.viewer = self._user('solutions', 'viewer@example.com', 'viewer')
        self.other_staff = self._user(
            'personal-training', 'other@example.com', 'staff'
        )
        ai_settings.update_settings(
            self.owner,
            'solutions',
            enabled=True,
            max_input_units=8000,
            max_output_units=1000,
            rolling_limit_units=40000,
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

    def test_lexical_search_returns_source_verifiable_tenant_hits(self):
        company = crm_companies.create_company(
            'solutions',
            name='Acme Cloud',
            industry='Technology',
            notes='Kubernetes migration roadmap',
        )
        result = ai_knowledge.search_knowledge(
            self.staff,
            'solutions',
            query='kubernetes migration',
            source_classes=('crm_company',),
        )
        self.assertIsNone(result.answer)
        self.assertEqual(1, len(result.hits))
        self.assertEqual(
            'crm_company',
            result.hits[0].reference.context_class,
        )
        self.assertEqual(
            str(company.id),
            result.hits[0].reference.identifier,
        )

    def test_cross_tenant_records_are_not_retrievable(self):
        crm_companies.create_company(
            'personal-training',
            name='Foreign Kubernetes',
            notes='foreign tenant secret migration',
        )
        result = ai_knowledge.search_knowledge(
            self.staff,
            'solutions',
            query='foreign tenant secret',
            source_classes=('crm_company',),
        )
        self.assertEqual((), result.hits)

    def test_site_scope_prevents_other_site_retrieval(self):
        tenant_sites.create_site(
            'solutions', slug='second', name='Second'
        )
        site_pages.create_page(
            'solutions',
            'main',
            slug='main-ai',
            title='Main Knowledge',
            body='alpha knowledge',
        )
        site_pages.create_page(
            'solutions',
            'second',
            slug='second-ai',
            title='Second Knowledge',
            body='beta hidden',
        )
        result = ai_knowledge.search_knowledge(
            self.staff,
            'solutions',
            query='beta hidden',
            site_slug='main',
            source_classes=('site_page',),
        )
        self.assertEqual((), result.hits)

    def test_viewer_is_denied_knowledge_search(self):
        with self.assertRaises(PermissionError):
            ai_knowledge.search_knowledge(
                self.viewer,
                'solutions',
                query='anything',
            )

    def test_staff_conversation_search_can_retrieve_internal_staff_knowledge(self):
        conversation = tenant_conversations.create_conversation(
            tenant_slug='solutions',
            kind='chat',
            name='Customer',
            email='customer@example.com',
            body='Customer asks about migration.',
            subject='Migration',
        )
        tenant_conversations.add_message(
            'solutions',
            conversation['token'],
            body='Internal runbook says use blue-green deployment.',
            sender='Staff',
            sender_type='admin',
            internal=True,
        )
        result = ai_knowledge.search_knowledge(
            self.staff,
            'solutions',
            query='blue-green deployment',
            source_classes=('conversation',),
        )
        self.assertEqual(1, len(result.hits))
        self.assertIn('internal', result.hits[0].snippet)

    def test_provider_answer_receives_only_retrieved_tenant_records(self):
        crm_companies.create_company(
            'solutions',
            name='Acme',
            notes='Use immutable infrastructure for production.',
        )
        crm_companies.create_company(
            'personal-training',
            name='Foreign',
            notes='DO NOT LEAK FOREIGN TENANT',
        )
        provider = FakeProvider()
        result = ai_knowledge.search_knowledge(
            self.staff,
            'solutions',
            query='immutable infrastructure',
            provider=provider,
            source_classes=('crm_company',),
        )
        self.assertEqual(
            'Answer from retrieved tenant records',
            result.answer,
        )
        self.assertEqual(
            'untrusted_generated_text',
            result.output_classification,
        )
        self.assertEqual(1, len(provider.calls))
        self.assertIn('immutable infrastructure', provider.calls[0])
        self.assertNotIn('DO NOT LEAK FOREIGN TENANT', provider.calls[0])
        self.assertIn('[crm_company:', provider.calls[0])

    def test_unknown_source_class_fails_closed(self):
        with self.assertRaises(ValueError):
            ai_knowledge.search_knowledge(
                self.staff,
                'solutions',
                query='test',
                source_classes=('external_web',),
            )


if __name__ == '__main__':
    unittest.main()
