from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import ai_execution
import ai_settings
import billing_plans
import tenant_auth
import tenant_sites


class FakeProvider:
    provider_name = 'fake'
    model_id = 'fake-1'

    def __init__(self):
        self.calls = 0

    def generate(
        self,
        prompt,
        *,
        max_output_units,
        timeout_seconds,
    ):
        self.calls += 1
        return ai_execution.ProviderResult(
            text='ok',
            input_units=2,
            output_units=2,
        )


class Sprint8CommercializationEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

        self.owner = self._user(
            'solutions', 'owner@example.com', 'owner'
        )
        self.staff = self._user(
            'solutions', 'staff@example.com', 'staff'
        )
        self.other_owner = self._user(
            'adventures', 'other@example.com', 'owner'
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _user(self, org_slug, email, role):
        with tenant_auth.db() as conn:
            org = conn.execute(
                'SELECT id FROM auth_organizations WHERE slug=?',
                (org_slug,),
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
                    now, now, org['id'], email, 'Quota', 'User',
                    tenant_auth.hash_password('abcdefghijkl'), role,
                ),
            )
            uid = int(cur.lastrowid)
            conn.execute(
                '''INSERT INTO auth_memberships(
                       created_at,updated_at,user_id,organization_id,
                       role_id,status
                   ) VALUES(?,?,?,?,?,'active')''',
                (now, now, uid, org['id'], role_row['id']),
            )
            conn.commit()
        return uid

    def _plan(
        self,
        *,
        slug='commercial',
        sites=1,
        ai=True,
        ai_units=100,
    ):
        return billing_plans.create_plan(
            self.owner,
            'solutions',
            slug=slug,
            name=slug.title(),
            entitlements={
                'sites': sites,
                'crm': True,
                'portal': True,
                'creator': True,
                'ai': ai,
                'ai_rolling_units': ai_units,
            },
        )

    def test_internal_tenant_without_plan_keeps_unlimited_site_policy(self):
        tenant_sites.create_site(
            'adventures', slug='one', name='One'
        )
        tenant_sites.create_site(
            'adventures', slug='two', name='Two'
        )
        self.assertEqual(
            3,
            len(tenant_sites.list_sites('adventures')),
        )

    def test_assigned_plan_enforces_non_archived_site_quota(self):
        self._plan(sites=1)
        billing_plans.assign_plan(
            self.owner, 'solutions', 'commercial'
        )
        with self.assertRaises(PermissionError):
            tenant_sites.create_site(
                'solutions', slug='blocked', name='Blocked'
            )

        tenant_sites.archive_site('solutions', 'main')
        created = tenant_sites.create_site(
            'solutions', slug='replacement', name='Replacement'
        )
        self.assertEqual('replacement', created.slug)

    def test_disabled_plan_ai_blocks_before_provider_call(self):
        self._plan(ai=False)
        billing_plans.assign_plan(
            self.owner, 'solutions', 'commercial'
        )
        ai_settings.update_settings(
            self.owner,
            'solutions',
            enabled=True,
            rolling_limit_units=1000,
        )
        provider = FakeProvider()
        with self.assertRaises(PermissionError):
            ai_execution.execute(
                self.staff,
                'solutions',
                task_type='draft',
                prompt='hello',
                requested_input_units=2,
                requested_output_units=2,
                provider=provider,
            )
        self.assertEqual(0, provider.calls)

    def test_plan_ai_rolling_quota_blocks_before_provider_call(self):
        self._plan(ai=True, ai_units=10)
        billing_plans.assign_plan(
            self.owner, 'solutions', 'commercial'
        )
        ai_settings.update_settings(
            self.owner,
            'solutions',
            enabled=True,
            rolling_limit_units=1000,
        )
        provider = FakeProvider()
        with self.assertRaises(PermissionError):
            ai_execution.execute(
                self.staff,
                'solutions',
                task_type='draft',
                prompt='hello',
                requested_input_units=6,
                requested_output_units=5,
                provider=provider,
            )
        self.assertEqual(0, provider.calls)

    def test_tenant_ai_setting_can_be_stricter_than_plan(self):
        self._plan(ai=True, ai_units=100)
        billing_plans.assign_plan(
            self.owner, 'solutions', 'commercial'
        )
        ai_settings.update_settings(
            self.owner,
            'solutions',
            enabled=True,
            rolling_limit_units=10,
        )
        provider = FakeProvider()
        with self.assertRaises(PermissionError):
            ai_execution.execute(
                self.staff,
                'solutions',
                task_type='draft',
                prompt='hello',
                requested_input_units=6,
                requested_output_units=5,
                provider=provider,
            )
        self.assertEqual(0, provider.calls)

    def test_internal_ai_policy_remains_provider_usable_when_enabled(self):
        ai_settings.update_settings(
            self.other_owner,
            'adventures',
            enabled=True,
            rolling_limit_units=1000,
        )
        provider = FakeProvider()
        result = ai_execution.execute(
            self.other_owner,
            'adventures',
            task_type='draft',
            prompt='hello',
            requested_input_units=2,
            requested_output_units=2,
            provider=provider,
        )
        self.assertEqual('ok', result.text)
        self.assertEqual(1, provider.calls)


if __name__ == '__main__':
    unittest.main()
