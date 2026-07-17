from pathlib import Path
import importlib
import sys
import tempfile
import unittest

SITE_DIR = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SITE_DIR) not in sys.path:
    sys.path.insert(0, str(SITE_DIR))

import messaging
import tenant_auth
import tenant_context
import tenant_lifecycle
import tenant_organizations


class Sprint2TenantLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        messaging.DATA_DIR = data
        messaging.DB_PATH = data / 'madmallard.sqlite3'
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        importlib.reload(tenant_context)
        importlib.reload(tenant_organizations)
        importlib.reload(tenant_lifecycle)
        ok, message = tenant_organizations.create_organization(
            slug='lifecycle-test',
            name='Lifecycle Test',
            primary_domain='lifecycle.example.com',
        )
        self.assertTrue(ok, message)

    def tearDown(self):
        self.tmp.cleanup()

    def add_user_state(self):
        with tenant_auth.db() as conn:
            organization = conn.execute(
                "SELECT id FROM auth_organizations WHERE slug = 'lifecycle-test'"
            ).fetchone()
            timestamp = tenant_auth.now()
            cursor = conn.execute(
                '''INSERT INTO auth_users(
                       created_at, updated_at, organization_id, email,
                       first_name, last_name, password_hash, role, is_active
                   ) VALUES (?, ?, ?, ?, 'Test', 'Owner', ?, 'owner', 1)''',
                (
                    timestamp,
                    timestamp,
                    organization['id'],
                    'owner@example.com',
                    tenant_auth.hash_password('LifecyclePass123!'),
                ),
            )
            user_id = int(cursor.lastrowid)
            conn.execute(
                '''INSERT INTO auth_sessions(
                       created_at, updated_at, user_id, token_hash, expires_at
                   ) VALUES (?, ?, ?, 'session-hash', ?)''',
                (timestamp, timestamp, user_id, timestamp + 3600),
            )
            conn.execute(
                '''INSERT INTO auth_tokens(
                       created_at, updated_at, user_id, purpose, token_hash, expires_at
                   ) VALUES (?, ?, ?, 'reset_password', 'token-hash', ?)''',
                (timestamp, timestamp, user_id, timestamp + 3600),
            )
            conn.commit()

    def test_suspend_disables_domain_resolution(self):
        ok, _, result = tenant_lifecycle.suspend_tenant('lifecycle-test')
        self.assertTrue(ok)
        self.assertEqual(result.current_status, 'inactive')
        self.assertFalse(result.domains_active)
        self.assertIsNone(tenant_context.resolve_tenant('lifecycle.example.com'))

    def test_suspend_revokes_sessions_and_tokens(self):
        self.add_user_state()
        ok, _, result = tenant_lifecycle.suspend_tenant('lifecycle-test')
        self.assertTrue(ok)
        self.assertEqual(result.sessions_revoked, 1)
        self.assertEqual(result.tokens_revoked, 1)
        with tenant_auth.db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM auth_sessions').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM auth_tokens').fetchone()[0], 0)

    def test_reactivate_restores_domains(self):
        self.assertTrue(tenant_lifecycle.suspend_tenant('lifecycle-test')[0])
        ok, _, result = tenant_lifecycle.reactivate_tenant('lifecycle-test')
        self.assertTrue(ok)
        self.assertEqual(result.previous_status, 'inactive')
        self.assertTrue(result.domains_active)
        self.assertEqual(
            tenant_context.resolve_tenant('lifecycle.example.com').slug,
            'lifecycle-test',
        )

    def test_archive_preserves_tenant_data(self):
        ok, _, result = tenant_lifecycle.archive_tenant('lifecycle-test')
        self.assertTrue(ok)
        self.assertEqual(result.current_status, 'archived')
        row = tenant_organizations.get_organization('lifecycle-test')
        self.assertEqual(row['status'], 'archived')
        self.assertIsNone(tenant_context.resolve_tenant('lifecycle.example.com'))

    def test_primary_tenant_cannot_be_suspended_or_archived(self):
        self.assertFalse(tenant_lifecycle.suspend_tenant('solutions')[0])
        self.assertFalse(tenant_lifecycle.archive_tenant('solutions')[0])
        self.assertEqual(tenant_context.resolve_tenant(tenant_auth.PRIMARY_DOMAIN).slug, 'solutions')

    def test_invalid_and_duplicate_transitions_are_rejected(self):
        self.assertFalse(
            tenant_lifecycle.change_tenant_status('lifecycle-test', 'delete')[0]
        )
        self.assertTrue(tenant_lifecycle.suspend_tenant('lifecycle-test')[0])
        self.assertFalse(tenant_lifecycle.suspend_tenant('lifecycle-test')[0])
        self.assertFalse(tenant_lifecycle.suspend_tenant('missing-tenant')[0])


if __name__ == '__main__':
    unittest.main()
