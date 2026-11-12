from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import ai_settings
import tenant_auth
import tenant_memberships
import tenant_sites


class Sprint7AISettingsTests(unittest.TestCase):
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
                'SELECT id FROM auth_roles WHERE slug=?', (role,)
            ).fetchone()
            now = tenant_auth.now()
            cur = conn.execute(
                '''INSERT INTO auth_users(
                       created_at,updated_at,organization_id,email,
                       first_name,last_name,password_hash,role,is_active
                   ) VALUES(?,?,?,?,?,?,?,?,1)''',
                (
                    now, now, org['id'], email, role.title(), 'User',
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

    def test_ai_is_disabled_by_default(self):
        settings = ai_settings.get_settings('solutions')
        self.assertFalse(settings.enabled)

    def test_owner_and_admin_can_update_limits(self):
        owner = ai_settings.update_settings(
            self.users['owner'], 'solutions',
            enabled=True,
            max_input_units=2000,
            max_output_units=500,
            rolling_limit_units=10000,
        )
        self.assertTrue(owner.enabled)
        self.assertEqual(2000, owner.max_input_units)

        admin = ai_settings.update_settings(
            self.users['admin'], 'solutions',
            enabled=True,
            max_input_units=2500,
            max_output_units=600,
            rolling_limit_units=12000,
        )
        self.assertEqual(2500, admin.max_input_units)

    def test_staff_and_viewer_cannot_change_settings(self):
        for role in ('staff', 'viewer'):
            with self.assertRaises(PermissionError):
                ai_settings.update_settings(
                    self.users[role], 'solutions', enabled=True
                )

    def test_limits_are_bounded(self):
        with self.assertRaises(ValueError):
            ai_settings.update_settings(
                self.users['owner'], 'solutions',
                enabled=True, max_input_units=0
            )
        with self.assertRaises(ValueError):
            ai_settings.update_settings(
                self.users['owner'], 'solutions',
                enabled=True,
                max_output_units=ai_settings.MAX_OUTPUT_UNITS + 1
            )
        with self.assertRaises(ValueError):
            ai_settings.update_settings(
                self.users['owner'], 'solutions',
                enabled=True,
                rolling_limit_units=ai_settings.MAX_ROLLING_LIMIT_UNITS + 1
            )

    def test_usage_checks_require_enablement_and_respect_all_limits(self):
        with self.assertRaises(PermissionError):
            ai_settings.require_usage_allowed(
                self.users['staff'], 'solutions',
                requested_input_units=100,
                requested_output_units=50,
            )

        ai_settings.update_settings(
            self.users['owner'], 'solutions',
            enabled=True,
            max_input_units=1000,
            max_output_units=200,
            rolling_limit_units=1500,
        )
        scope, settings = ai_settings.require_usage_allowed(
            self.users['staff'], 'solutions',
            requested_input_units=800,
            requested_output_units=100,
            rolling_used_units=500,
        )
        self.assertEqual('solutions', scope.organization_slug)
        self.assertTrue(settings.enabled)

        with self.assertRaises(PermissionError):
            ai_settings.require_usage_allowed(
                self.users['staff'], 'solutions',
                requested_input_units=1001,
                requested_output_units=100,
            )
        with self.assertRaises(PermissionError):
            ai_settings.require_usage_allowed(
                self.users['staff'], 'solutions',
                requested_input_units=100,
                requested_output_units=201,
            )
        with self.assertRaises(PermissionError):
            ai_settings.require_usage_allowed(
                self.users['staff'], 'solutions',
                requested_input_units=800,
                requested_output_units=100,
                rolling_used_units=700,
            )

    def test_cross_tenant_and_inactive_tenant_checks_fail_closed(self):
        with self.assertRaises(PermissionError):
            ai_settings.update_settings(
                self.users['owner'], 'personal-training', enabled=True
            )

        tenant_memberships.grant_membership(
            self.users['owner'], 'personal-training', 'owner'
        )
        ai_settings.update_settings(
            self.users['owner'], 'personal-training', enabled=True
        )
        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_organizations SET status='suspended' "
                "WHERE slug='personal-training'"
            )
            conn.commit()
        with self.assertRaises(PermissionError):
            ai_settings.require_usage_allowed(
                self.users['owner'], 'personal-training',
                requested_input_units=1,
                requested_output_units=1,
            )


if __name__ == '__main__':
    unittest.main()
