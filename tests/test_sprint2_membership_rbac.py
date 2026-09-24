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
import tenant_auth
import tenant_context
import tenant_memberships
import tenant_onboarding


class Sprint2MembershipRbacFoundationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        messaging.DATA_DIR = data
        messaging.DB_PATH = data / 'madmallard.sqlite3'
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        importlib.reload(tenant_context)
        importlib.reload(tenant_memberships)
        importlib.reload(tenant_onboarding)

    def tearDown(self):
        self.tmp.cleanup()

    def register(self, organization='solutions', email='member@example.com'):
        with patch.object(messaging, 'send_email', return_value=True):
            ok, message = tenant_auth.register_user(
                organization_slug=organization,
                first_name='Casey',
                last_name='Member',
                email=email,
                password='VerySecurePass123!',
                public_host='pillar.madmallards.com',
            )
        self.assertTrue(ok, message)
        with tenant_auth.db() as conn:
            return int(conn.execute(
                '''SELECT u.id FROM auth_users u
                   JOIN auth_organizations o ON o.id = u.organization_id
                   WHERE o.slug = ? AND lower(u.email) = lower(?)''',
                (organization, email),
            ).fetchone()['id'])

    def test_schema_seeds_supported_roles(self):
        with tenant_auth.db() as conn:
            roles = {
                row['slug']
                for row in conn.execute('SELECT slug FROM auth_roles').fetchall()
            }
        self.assertEqual(roles, set(tenant_auth.ROLES))

    def test_registration_creates_viewer_membership(self):
        user_id = self.register()
        membership = tenant_memberships.get_membership(user_id, 'solutions')
        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, 'viewer')
        self.assertEqual(membership.status, 'active')

    def test_user_can_hold_memberships_in_multiple_organizations(self):
        user_id = self.register()
        ok, message, membership = tenant_memberships.grant_membership(
            user_id,
            'personal-training',
            'admin',
        )
        self.assertTrue(ok, message)
        self.assertEqual(membership.role, 'admin')
        self.assertEqual(
            {item.organization_slug for item in tenant_memberships.list_user_memberships(user_id)},
            {'solutions', 'personal-training'},
        )

    def test_membership_role_can_change_without_changing_primary_identity(self):
        user_id = self.register()
        self.assertTrue(
            tenant_memberships.grant_membership(user_id, 'adventures', 'staff')[0]
        )
        ok, message, membership = tenant_memberships.set_membership_role(
            user_id,
            'adventures',
            'admin',
        )
        self.assertTrue(ok, message)
        self.assertEqual(membership.role, 'admin')
        with tenant_auth.db() as conn:
            user = conn.execute(
                'SELECT role FROM auth_users WHERE id = ?',
                (user_id,),
            ).fetchone()
        self.assertEqual(user['role'], 'viewer')

    def test_revoked_membership_is_excluded_from_active_list(self):
        user_id = self.register()
        self.assertTrue(
            tenant_memberships.grant_membership(user_id, 'adventures', 'staff')[0]
        )
        ok, message, membership = tenant_memberships.revoke_membership(
            user_id,
            'adventures',
        )
        self.assertTrue(ok, message)
        self.assertEqual(membership.status, 'revoked')
        self.assertNotIn(
            'adventures',
            {item.organization_slug for item in tenant_memberships.list_user_memberships(user_id)},
        )

    def test_invalid_role_is_rejected(self):
        user_id = self.register()
        ok, message, membership = tenant_memberships.grant_membership(
            user_id,
            'adventures',
            'superuser',
        )
        self.assertFalse(ok)
        self.assertIn('valid', message.lower())
        self.assertIsNone(membership)

    def test_onboarding_creates_owner_membership(self):
        with patch.object(messaging, 'send_email', return_value=True):
            ok, message, _ = tenant_onboarding.onboard_tenant(
                slug='rbac-client',
                organization_name='RBAC Client',
                primary_domain='rbac.example.com',
                owner_first_name='Taylor',
                owner_last_name='Owner',
                owner_email='owner@rbac.example.com',
                owner_password='VerySecurePass123!',
            )
        self.assertTrue(ok, message)
        with tenant_auth.db() as conn:
            owner_id = int(conn.execute(
                "SELECT id FROM auth_users WHERE lower(email) = 'owner@rbac.example.com'"
            ).fetchone()['id'])
        membership = tenant_memberships.get_membership(owner_id, 'rbac-client')
        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, 'owner')
        self.assertTrue(
            tenant_memberships.has_role(owner_id, 'rbac-client', 'owner')
        )


if __name__ == '__main__':
    unittest.main()
