from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import ai_boundary
import ai_drafting
import ai_execution
import ai_settings
import creator_profiles
import crm_companies
import site_pages
import tenant_auth
import tenant_sites


class FakeProvider:
    provider_name = 'fake-provider'
    model_id = 'fake-draft-model'

    def __init__(self):
        self.calls = []

    def generate(self, prompt, *, max_output_units, timeout_seconds):
        self.calls.append(
            {
                'prompt': prompt,
                'max_output_units': max_output_units,
                'timeout_seconds': timeout_seconds,
            }
        )
        return ai_execution.ProviderResult(
            text='Human-review draft',
            input_units=max(1, (len(prompt) + 3) // 4),
            output_units=30,
        )


class Sprint7AIDraftingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()
        self.owner = self._user('solutions', 'owner@example.com', 'owner')
        self.staff = self._user('solutions', 'staff@example.com', 'staff')
        self.other = self._user(
            'personal-training', 'other@example.com', 'staff'
        )
        ai_settings.update_settings(
            self.owner,
            'solutions',
            enabled=True,
            max_input_units=5000,
            max_output_units=1000,
            rolling_limit_units=20000,
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

    def test_draft_returns_untrusted_reviewable_text_without_mutating_sources(self):
        company = crm_companies.create_company(
            'solutions',
            name='Acme',
            industry='Technology',
            notes='Needs a migration proposal.',
        )
        page = site_pages.create_page(
            'solutions',
            'main',
            slug='services-ai',
            title='Services',
            summary='Cloud services',
            body='Existing canonical body',
        )
        before_company = crm_companies.get_company('solutions', company.id)
        before_page = site_pages.get_page(
            'solutions', 'main', 'services-ai'
        )
        provider = FakeProvider()

        result = ai_drafting.draft_text(
            self.staff,
            'solutions',
            instructions='Draft a concise introductory paragraph.',
            references=(
                ai_boundary.AIContextReference(
                    'crm_company', str(company.id)
                ),
                ai_boundary.AIContextReference(
                    'site_page', 'services-ai', site_slug='main'
                ),
            ),
            provider=provider,
            site_slug='main',
            requested_output_units=200,
        )

        self.assertEqual('Human-review draft', result.text)
        self.assertEqual(
            ai_boundary.OUTPUT_CLASSIFICATION,
            result.output_classification,
        )
        self.assertEqual(2, len(result.source_references))
        self.assertEqual(1, len(provider.calls))
        self.assertIn('Acme', provider.calls[0]['prompt'])
        self.assertIn('Existing canonical body', provider.calls[0]['prompt'])

        after_company = crm_companies.get_company('solutions', company.id)
        after_page = site_pages.get_page(
            'solutions', 'main', 'services-ai'
        )
        self.assertEqual(before_company, after_company)
        self.assertEqual(before_page, after_page)

    def test_creator_profile_context_is_explicit_and_not_auto_published(self):
        profile = creator_profiles.upsert_profile(
            'solutions',
            'main',
            display_name='Draft Creator',
            bio='Original biography',
            status='draft',
        )
        provider = FakeProvider()
        result = ai_drafting.draft_text(
            self.staff,
            'solutions',
            instructions='Suggest a revised bio.',
            references=(
                ai_boundary.AIContextReference(
                    'creator_profile', 'profile', site_slug='main'
                ),
            ),
            provider=provider,
            site_slug='main',
        )
        self.assertEqual('Human-review draft', result.text)
        after = creator_profiles.get_profile('solutions', 'main')
        self.assertEqual(profile, after)
        self.assertEqual('draft', after.status)

    def test_cross_tenant_reference_is_rejected_before_provider_call(self):
        foreign = crm_companies.create_company(
            'personal-training',
            name='Foreign Company',
        )
        provider = FakeProvider()
        with self.assertRaises(PermissionError):
            ai_drafting.draft_text(
                self.staff,
                'solutions',
                instructions='Draft text.',
                references=(
                    ai_boundary.AIContextReference(
                        'crm_company', str(foreign.id)
                    ),
                ),
                provider=provider,
            )
        self.assertEqual([], provider.calls)

    def test_disabled_ai_preserves_manual_workflow_and_does_not_call_provider(self):
        ai_settings.update_settings(
            self.owner,
            'solutions',
            enabled=False,
        )
        company = crm_companies.create_company(
            'solutions',
            name='Manual Company',
        )
        provider = FakeProvider()
        with self.assertRaises(PermissionError):
            ai_drafting.draft_text(
                self.staff,
                'solutions',
                instructions='Draft text.',
                references=(
                    ai_boundary.AIContextReference(
                        'crm_company', str(company.id)
                    ),
                ),
                provider=provider,
            )
        self.assertEqual([], provider.calls)
        self.assertIsNotNone(
            crm_companies.get_company('solutions', company.id)
        )

    def test_instructions_and_context_are_bounded(self):
        company = crm_companies.create_company(
            'solutions',
            name='Bounded',
            notes='x' * 100,
        )
        provider = FakeProvider()
        with self.assertRaises(ValueError):
            ai_drafting.draft_text(
                self.staff,
                'solutions',
                instructions='x' * (ai_drafting.MAX_INSTRUCTION_CHARS + 1),
                references=(
                    ai_boundary.AIContextReference(
                        'crm_company', str(company.id)
                    ),
                ),
                provider=provider,
            )
        self.assertEqual([], provider.calls)


if __name__ == '__main__':
    unittest.main()
