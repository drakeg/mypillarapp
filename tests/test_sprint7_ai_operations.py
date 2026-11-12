from __future__ import annotations

from pathlib import Path
import os
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import ai_admin
import ai_execution
import ai_settings
import tenant_auth
import tenant_sites


class FakeProvider:
    provider_name = 'fake-provider'
    model_id = 'fake-ops-model'

    def __init__(self, mode='success'):
        self.mode = mode
        self.calls = 0

    def generate(self, prompt, *, max_output_units, timeout_seconds):
        self.calls += 1
        if self.mode == 'timeout':
            raise TimeoutError('simulated timeout')
        if self.mode == 'error':
            raise RuntimeError('simulated failure')
        return ai_execution.ProviderResult(
            text='ok',
            input_units=10,
            output_units=5,
        )


class Sprint7AIOperationalSafeguardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()
        self.owner = self._user('owner@example.com', 'owner')
        self.staff = self._user('staff@example.com', 'staff')
        ai_settings.update_settings(
            self.owner,
            'solutions',
            enabled=True,
            max_input_units=100,
            max_output_units=50,
            rolling_limit_units=200,
        )
        os.environ.pop(ai_execution.AI_KILL_SWITCH_ENV, None)

    def tearDown(self):
        os.environ.pop(ai_execution.AI_KILL_SWITCH_ENV, None)
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

    def _execute(self, provider, *, input_units=10, output_units=5):
        return ai_execution.execute(
            self.staff,
            'solutions',
            task_type='draft',
            prompt='hello',
            requested_input_units=input_units,
            requested_output_units=output_units,
            provider=provider,
        )

    def test_kill_switch_rejects_before_provider_and_records_status(self):
        os.environ[ai_execution.AI_KILL_SWITCH_ENV] = 'true'
        provider = FakeProvider()
        with self.assertRaises(PermissionError):
            self._execute(provider)
        self.assertEqual(0, provider.calls)
        usage = ai_admin.usage_records(self.owner, 'solutions')
        self.assertEqual('rejected_before_call', usage[0].status)

    def test_quota_limit_rejection_is_recorded_before_provider_call(self):
        provider = FakeProvider()
        with self.assertRaises(PermissionError):
            self._execute(provider, input_units=101)
        self.assertEqual(0, provider.calls)
        usage = ai_admin.usage_records(self.owner, 'solutions')
        self.assertEqual('quota_limit', usage[0].status)

    def test_provider_error_and_timeout_statuses_remain_content_free(self):
        for mode, expected in (
            ('error', 'provider_error'),
            ('timeout', 'timeout'),
        ):
            with self.assertRaises(ai_execution.AIExecutionError):
                self._execute(FakeProvider(mode=mode))
            self.assertEqual(
                expected,
                ai_admin.usage_records(self.owner, 'solutions', limit=1)[0].status,
            )

        with tenant_auth.db() as conn:
            columns = {
                row['name']
                for row in conn.execute(
                    'PRAGMA table_info(ai_usage_events)'
                ).fetchall()
            }
        self.assertNotIn('prompt', columns)
        self.assertNotIn('response', columns)
        self.assertNotIn('secret', columns)
        self.assertNotIn('session_token', columns)

    def test_operational_summary_reports_task_model_status_and_failure_rate(self):
        self._execute(FakeProvider())
        with self.assertRaises(ai_execution.AIExecutionError):
            self._execute(FakeProvider(mode='error'))
        summary = ai_admin.operational_summary(
            self.owner,
            'solutions',
        )
        self.assertEqual(2, summary.total_events)
        self.assertEqual(1, summary.successful_events)
        self.assertEqual(1, summary.failed_events)
        self.assertAlmostEqual(0.5, summary.failure_rate)
        self.assertEqual(2, summary.by_task['draft'])
        self.assertEqual(2, summary.by_model['fake-ops-model'])
        self.assertEqual(1, summary.by_status['success'])
        self.assertEqual(1, summary.by_status['provider_error'])

    def test_schema_migrates_existing_usage_rows_to_expanded_status_constraint(self):
        ai_execution.ensure_schema()
        with tenant_auth.db() as conn:
            sql = conn.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type='table' AND name='ai_usage_events'"
            ).fetchone()['sql']
        self.assertIn('rejected_before_call', sql)
        self.assertIn('quota_limit', sql)


if __name__ == '__main__':
    unittest.main()
