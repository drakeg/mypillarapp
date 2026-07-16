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


class Sprint2TenantUserIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)

        importlib.reload(tenant_auth)
        messaging.DATA_DIR = data
        messaging.DB_PATH = data / 'madmallard.sqlite3'
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        messaging.send_email = lambda *args, **kwargs: True

    def tearDown(self):
        self.tmp.cleanup()

    def register(self, tenant, email, password):
        return tenant_auth.register_user(
            organization_slug=tenant,
            first_name='Test',
            last_name='User',
            email=email,
            password=password,
            public_host=f'{tenant}.example.com',
        )

    def activate(self):
        with tenant_auth.db() as conn:
            conn.execute('UPDATE auth_users SET is_active = 1')
            conn.commit()

    def test_same_email_can_register_in_two_tenants(self):
        self.assertTrue(self.register('solutions', 'shared@example.com', 'SolutionsPass123!')[0])
        self.assertTrue(self.register('adventures', 'shared@example.com', 'AdventurePass123!')[0])

    def test_duplicate_email_is_rejected_within_tenant(self):
        self.assertTrue(self.register('solutions', 'same@example.com', 'FirstPassword123!')[0])
        self.assertFalse(self.register('solutions', 'same@example.com', 'SecondPassword123!')[0])

    def test_login_is_tenant_scoped(self):
        self.register('solutions', 'shared@example.com', 'SolutionsPass123!')
        self.register('adventures', 'shared@example.com', 'AdventurePass123!')
        self.activate()

        self.assertTrue(tenant_auth.login_user('shared@example.com', 'SolutionsPass123!', 'solutions')[0])
        self.assertFalse(tenant_auth.login_user('shared@example.com', 'SolutionsPass123!', 'adventures')[0])
        self.assertTrue(tenant_auth.login_user('shared@example.com', 'AdventurePass123!', 'adventures')[0])

    def test_profile_uniqueness_is_tenant_scoped(self):
        self.register('solutions', 'one@example.com', 'SolutionsPass123!')
        self.register('adventures', 'target@example.com', 'AdventurePass123!')
        with tenant_auth.db() as conn:
            user = conn.execute(
                """SELECT u.id
                   FROM auth_users u
                   JOIN auth_organizations o ON o.id = u.organization_id
                   WHERE o.slug = 'solutions'"""
            ).fetchone()
        self.assertTrue(tenant_auth.update_profile(user['id'], 'Test', 'User', 'target@example.com')[0])

    def test_composite_unique_index_exists(self):
        with tenant_auth.db() as conn:
            indexes = conn.execute('PRAGMA index_list(auth_users)').fetchall()
            unique = []
            for index in indexes:
                if index['unique']:
                    unique.append(
                        [
                            column['name']
                            for column in conn.execute(
                                f"PRAGMA index_info({index['name']})"
                            ).fetchall()
                        ]
                    )
        self.assertIn(['organization_id', 'email'], unique)
        self.assertNotIn(['email'], unique)


if __name__ == '__main__':
    unittest.main()
