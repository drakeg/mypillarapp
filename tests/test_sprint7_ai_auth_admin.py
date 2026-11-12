from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import ai_admin
import ai_auth
import ai_settings
import tenant_auth
import tenant_memberships
import tenant_sites


class Sprint7AIAuthorizationAdminTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()
        self.users = {
            role: self._user(f'{role}@example.com', role)
            for role in ('owner', 'admin', 'staff', 'viewer')
        }

    def tearDown(self):
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

    def test_capability_matrix_is_least_privilege_and_unknown_fails_closed(self):
        for role in ('owner', 'admin', 'staff'):
            self.assertTrue(
                ai_auth.can(self.users[role], 'solutions', 'draft')
            )
            self.assertTrue(
                ai_auth.can(self.users[role], 'solutions', 'summary')
            )
            self.assertTrue(
                ai_auth.can(
                    self.users[role], 'solutions', 'knowledge_search'
                )
            )

        self.assertFalse(
            ai_auth.can(self.users['viewer'], 'solutions', 'draft')
        )
        self.assertTrue(
            ai_auth.can(self.users['viewer'], 'solutions', 'view_status')
        )
        self.assertFalse(
            ai_auth.can(self.users['viewer'], 'solutions', 'view_usage')
        )
        self.assertFalse(
            ai_auth.can(self.users['staff'], 'solutions', 'manage_settings')
        )
        self.assertTrue(
            ai_auth.can(self.users['owner'], 'solutions', 'manage_settings')
        )
        self.assertFalse(
            ai_auth.can(self.users['owner'], 'solutions', 'unknown')
        )

    def test_viewer_has_read_only_status_but_not_admin_operations(self):
        status = ai_admin.status_for(
            self.users['viewer'], 'solutions'
        )
        self.assertEqual('viewer', status.role)
        self.assertFalse(status.can_use)
        self.assertFalse(status.can_administer)

        with self.assertRaises(PermissionError):
            ai_admin.update_settings(
                self.users['viewer'], 'solutions', enabled=True
            )
        with self.assertRaises(PermissionError):
            ai_admin.usage_records(
                self.users['viewer'], 'solutions'
            )

    def test_owner_and_admin_can_manage_settings_and_view_usage(self):
        updated = ai_admin.update_settings(
            self.users['owner'],
            'solutions',
            enabled=True,
            max_input_units=2000,
            max_output_units=500,
            rolling_limit_units=10000,
        )
        self.assertTrue(updated.enabled)

        status = ai_admin.status_for(
            self.users['admin'], 'solutions'
        )
        self.assertTrue(status.enabled)
        self.assertTrue(status.can_administer)
        self.assertEqual(2000, status.max_input_units)
        self.assertEqual(
            [],
            ai_admin.usage_records(
                self.users['admin'], 'solutions'
            ),
        )

    def test_staff_can_use_assistance_but_cannot_change_limits_or_view_usage(self):
        access = ai_auth.require(
            self.users['staff'], 'solutions', 'draft'
        )
        self.assertTrue(access.can_use)
        self.assertFalse(access.can_administer)

        with self.assertRaises(PermissionError):
            ai_admin.update_settings(
                self.users['staff'],
                'solutions',
                enabled=True,
                max_input_units=ai_settings.MAX_INPUT_UNITS,
            )
        with self.assertRaises(PermissionError):
            ai_admin.usage_records(
                self.users['staff'], 'solutions'
            )

    def test_revoked_disabled_and_suspended_states_fail_closed(self):
        tenant_memberships.revoke_membership(
            self.users['staff'], 'solutions'
        )
        self.assertFalse(
            ai_auth.can(self.users['staff'], 'solutions', 'draft')
        )

        with tenant_auth.db() as conn:
            conn.execute(
                'UPDATE auth_users SET is_active=0 WHERE id=?',
                (self.users['admin'],),
            )
            conn.commit()
        self.assertFalse(
            ai_auth.can(
                self.users['admin'], 'solutions', 'manage_settings'
            )
        )

        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_organizations SET status='suspended' "
                "WHERE slug='solutions'"
            )
            conn.commit()
        self.assertFalse(
            ai_auth.can(
                self.users['owner'], 'solutions', 'view_status'
            )
        )

    def test_archived_site_fails_closed_for_site_scoped_capability(self):
        tenant_sites.create_site(
            'solutions', slug='archive-ai', name='Archive AI'
        )
        tenant_sites.archive_site('solutions', 'archive-ai')
        self.assertFalse(
            ai_auth.can(
                self.users['owner'],
                'solutions',
                'draft',
                site_slug='archive-ai',
            )
        )
        with self.assertRaises(PermissionError):
            ai_auth.require_site_resource(
                self.users['owner'],
                'solutions',
                'archive-ai',
                'draft',
            )


if __name__ == '__main__':
    unittest.main()
