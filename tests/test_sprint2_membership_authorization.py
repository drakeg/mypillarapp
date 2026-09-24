from pathlib import Path
import importlib
import sys
import tempfile
import unittest
from unittest.mock import patch

SITE_DIR = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SITE_DIR) not in sys.path:
    sys.path.insert(0, str(SITE_DIR))

import messaging
import request_context
import tenant_auth
import tenant_context
import tenant_memberships


class Sprint2MembershipAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        messaging.DATA_DIR = data
        messaging.DB_PATH = data / 'madmallard.sqlite3'
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        importlib.reload(tenant_context)
        importlib.reload(tenant_memberships)
        importlib.reload(request_context)
        tenant_context.ensure_schema()
        tenant_context.register_domain(
            'personal-training',
            'fitness.example.test',
            primary=True,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def create_session(self):
        with patch.object(messaging, 'send_email', return_value=True):
            ok, message = tenant_auth.register_user(
                organization_slug='solutions',
                first_name='Casey',
                last_name='Member',
                email='casey@example.test',
                password='VerySecurePass123!',
                public_host='pillar.madmallards.com',
            )
        self.assertTrue(ok, message)
        with tenant_auth.db() as conn:
            row = conn.execute(
                "SELECT id FROM auth_users WHERE lower(email) = 'casey@example.test'"
            ).fetchone()
            user_id = int(row['id'])
            conn.execute(
                '''UPDATE auth_users
                   SET is_active = 1, email_verified_at = ?
                   WHERE id = ?''',
                (tenant_auth.now(), user_id),
            )
            conn.commit()
        ok, message, token = tenant_auth.login_user(
            'casey@example.test',
            'VerySecurePass123!',
            'solutions',
        )
        self.assertTrue(ok, message)
        return user_id, token

    def test_primary_tenant_session_uses_membership_role(self):
        user_id, token = self.create_session()
        self.assertTrue(
            tenant_memberships.set_membership_role(
                user_id,
                'solutions',
                'staff',
            )[0]
        )
        user = tenant_auth.current_user_for_tenant(token, 'solutions')
        self.assertIsNotNone(user)
        self.assertEqual(user['organization_slug'], 'solutions')
        self.assertEqual(user['role'], 'staff')

    def test_cross_tenant_membership_allows_tenant_login(self):
        user_id, _ = self.create_session()
        self.assertTrue(
            tenant_memberships.grant_membership(
                user_id,
                'personal-training',
                'viewer',
            )[0]
        )
        ok, message, token = tenant_auth.login_user(
            'casey@example.test',
            'VerySecurePass123!',
            'personal-training',
        )
        self.assertTrue(ok, message)
        self.assertTrue(token)
        user = tenant_auth.current_user_for_tenant(
            token,
            'personal-training',
        )
        self.assertIsNotNone(user)
        self.assertEqual(user['organization_slug'], 'personal-training')

    def test_revoked_membership_blocks_tenant_login(self):
        user_id, _ = self.create_session()
        self.assertTrue(
            tenant_memberships.grant_membership(
                user_id,
                'personal-training',
                'viewer',
            )[0]
        )
        self.assertTrue(
            tenant_memberships.revoke_membership(
                user_id,
                'personal-training',
            )[0]
        )
        ok, _, token = tenant_auth.login_user(
            'casey@example.test',
            'VerySecurePass123!',
            'personal-training',
        )
        self.assertFalse(ok)
        self.assertEqual(token, '')

    def test_cross_tenant_membership_authorizes_same_session(self):
        user_id, token = self.create_session()
        self.assertTrue(
            tenant_memberships.grant_membership(
                user_id,
                'personal-training',
                'admin',
            )[0]
        )
        user = tenant_auth.current_user_for_tenant(
            token,
            'personal-training',
        )
        self.assertIsNotNone(user)
        self.assertEqual(user['organization_slug'], 'personal-training')
        self.assertEqual(user['role'], 'admin')

    def test_missing_membership_denies_tenant_session(self):
        _, token = self.create_session()
        self.assertIsNone(
            tenant_auth.current_user_for_tenant(
                token,
                'personal-training',
            )
        )

    def test_revoked_membership_denies_tenant_session(self):
        user_id, token = self.create_session()
        self.assertTrue(
            tenant_memberships.grant_membership(
                user_id,
                'personal-training',
                'viewer',
            )[0]
        )
        self.assertTrue(
            tenant_memberships.revoke_membership(
                user_id,
                'personal-training',
            )[0]
        )
        self.assertIsNone(
            tenant_auth.current_user_for_tenant(
                token,
                'personal-training',
            )
        )

    def test_request_context_uses_resolved_tenant_membership(self):
        user_id, token = self.create_session()
        self.assertTrue(
            tenant_memberships.grant_membership(
                user_id,
                'personal-training',
                'viewer',
            )[0]
        )
        context = request_context.build_request_context(
            {'Host': 'fitness.example.test'},
            token,
        )
        self.assertIsNotNone(context)
        self.assertTrue(context.authenticated)
        self.assertEqual(context.tenant.slug, 'personal-training')
        self.assertEqual(context.user['organization_slug'], 'personal-training')
        self.assertEqual(context.user['role'], 'viewer')


if __name__ == '__main__':
    unittest.main()
