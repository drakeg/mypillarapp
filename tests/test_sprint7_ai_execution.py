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
import tenant_auth
import tenant_memberships
import tenant_sites


class FakeProvider:
    provider_name = 'fake-provider'
    model_id = 'fake-model-1'

    def __init__(self, *, mode='success'):
        self.mode = mode
        self.calls = []

    def generate(self, prompt, *, max_output_units, timeout_seconds):
        self.calls.append(
            {
                'prompt': prompt,
                'max_output_units': max_output_units,
                'timeout_seconds': timeout_seconds,
            }
        )
        if self.mode == 'timeout':
            raise TimeoutError('simulated timeout')
        if self.mode == 'error':
            raise RuntimeError('simulated provider failure')
        if self.mode == 'invalid':
            return object()
        return ai_execution.ProviderResult(
            text='Generated draft',
            input_units=120,
            output_units=40,
        )


class Sprint7AIExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

        self.owner = self._user('solutions', 'owner@example.com', 'owner')
        self.staff = self._user('solutions', 'staff@example.com', 'staff')
        self.other_staff = self._user(
            'personal-training', 'other@example.com', 'staff'
        )
        ai_settings.update_settings(
            self.owner,
            'solutions',
            enabled=True,
            max_input_units=1000,
            max_output_units=300,
            rolling_limit_units=1000,
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

    def test_successful_execution_uses_provider_interface_and_records_usage(self):
        provider = FakeProvider()
        result = ai_execution.execute(
            self.staff,
            'solutions',
            task_type='draft',
            prompt='Draft a concise reply.',
            requested_input_units=150,
            requested_output_units=100,
            provider=provider,
            timeout_seconds=12,
        )
        self.assertEqual('Generated draft', result.text)
        self.assertEqual('success', result.usage.status)
        self.assertEqual(160, result.usage.total_units)
        self.assertEqual('fake-provider', result.usage.provider_name)
        self.assertEqual('fake-model-1', result.usage.model_id)
        self.assertEqual(1, len(provider.calls))
        self.assertEqual(100, provider.calls[0]['max_output_units'])
        self.assertEqual(12, provider.calls[0]['timeout_seconds'])

    def test_raw_prompt_and_output_are_not_persisted_in_usage_table(self):
        provider = FakeProvider()
        ai_execution.execute(
            self.staff,
            'solutions',
            task_type='summary',
            prompt='SECRET PROMPT CONTENT',
            requested_input_units=150,
            requested_output_units=100,
            provider=provider,
        )
        with tenant_auth.db() as conn:
            columns = {
                row['name']
                for row in conn.execute(
                    'PRAGMA table_info(ai_usage_events)'
                ).fetchall()
            }
            row = conn.execute(
                'SELECT * FROM ai_usage_events ORDER BY id DESC LIMIT 1'
            ).fetchone()
        self.assertNotIn('prompt', columns)
        self.assertNotIn('response', columns)
        self.assertNotIn('provider_secret', columns)
        self.assertNotIn('SECRET PROMPT CONTENT', tuple(str(v) for v in row))
        self.assertNotIn('Generated draft', tuple(str(v) for v in row))

    def test_timeout_and_provider_error_return_controlled_errors_and_audit_status(self):
        for mode, status in (('timeout', 'timeout'), ('error', 'provider_error')):
            provider = FakeProvider(mode=mode)
            with self.assertRaises(ai_execution.AIExecutionError):
                ai_execution.execute(
                    self.staff,
                    'solutions',
                    task_type='summary',
                    prompt='Summarize',
                    requested_input_units=100,
                    requested_output_units=50,
                    provider=provider,
                    timeout_seconds=5,
                )
            usage = ai_execution.list_usage(
                self.staff, 'solutions', limit=1
            )[0]
            self.assertEqual(status, usage.status)

    def test_invalid_provider_response_fails_closed(self):
        with self.assertRaises(ai_execution.AIExecutionError):
            ai_execution.execute(
                self.staff,
                'solutions',
                task_type='draft',
                prompt='Draft',
                requested_input_units=100,
                requested_output_units=50,
                provider=FakeProvider(mode='invalid'),
            )
        usage = ai_execution.list_usage(
            self.staff, 'solutions', limit=1
        )[0]
        self.assertEqual('invalid_response', usage.status)

    def test_usage_accounting_enforces_rolling_limit_before_second_call(self):
        provider = FakeProvider()
        ai_settings.update_settings(
            self.owner,
            'solutions',
            enabled=True,
            max_input_units=1000,
            max_output_units=300,
            rolling_limit_units=250,
        )
        first = ai_execution.execute(
            self.staff,
            'solutions',
            task_type='draft',
            prompt='First',
            requested_input_units=150,
            requested_output_units=100,
            provider=provider,
        )
        self.assertEqual(160, first.usage.total_units)

        with self.assertRaises(PermissionError):
            ai_execution.execute(
                self.staff,
                'solutions',
                task_type='draft',
                prompt='Second',
                requested_input_units=100,
                requested_output_units=50,
                provider=provider,
            )
        self.assertEqual(1, len(provider.calls))

    def test_cross_tenant_usage_reads_fail_closed_without_membership(self):
        with self.assertRaises(PermissionError):
            ai_execution.list_usage(
                self.staff, 'personal-training'
            )

        tenant_memberships.grant_membership(
            self.staff, 'personal-training', 'viewer'
        )
        self.assertEqual(
            [],
            ai_execution.list_usage(
                self.staff, 'personal-training'
            ),
        )

    def test_disabled_ai_blocks_execution_before_provider_call(self):
        ai_settings.update_settings(
            self.owner,
            'solutions',
            enabled=False,
        )
        provider = FakeProvider()
        with self.assertRaises(PermissionError):
            ai_execution.execute(
                self.staff,
                'solutions',
                task_type='draft',
                prompt='Draft',
                requested_input_units=10,
                requested_output_units=10,
                provider=provider,
            )
        self.assertEqual([], provider.calls)

    def test_task_provider_model_and_timeout_inputs_are_bounded(self):
        provider = FakeProvider()
        with self.assertRaises(ValueError):
            ai_execution.execute(
                self.staff,
                'solutions',
                task_type='unknown',
                prompt='x',
                requested_input_units=1,
                requested_output_units=1,
                provider=provider,
            )
        with self.assertRaises(ValueError):
            ai_execution.execute(
                self.staff,
                'solutions',
                task_type='draft',
                prompt='x',
                requested_input_units=1,
                requested_output_units=1,
                provider=provider,
                timeout_seconds=0,
            )


if __name__ == '__main__':
    unittest.main()
