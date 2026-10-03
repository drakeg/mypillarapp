from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import crm_admin
import crm_auth
import tenant_auth
import tenant_memberships


class Sprint4CrmAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        with tenant_auth.db() as conn:
            org = conn.execute(
                "SELECT id FROM auth_organizations WHERE slug='solutions'"
            ).fetchone()
            role = conn.execute(
                "SELECT id FROM auth_roles WHERE slug='viewer'"
            ).fetchone()
            ts = tenant_auth.now()
            cur = conn.execute(
                """INSERT INTO auth_users(
                       created_at,updated_at,organization_id,email,first_name,last_name,
                       password_hash,role,is_active
                   ) VALUES(?,?,?,?,?,?,?,?,1)""",
                (
                    ts, ts, org['id'], 'crm-rbac@example.com', 'CRM', 'User',
                    tenant_auth.hash_password('abcdefghijkl'), 'viewer'
                ),
            )
            self.user_id = int(cur.lastrowid)
            conn.execute(
                """INSERT INTO auth_memberships(
                       created_at,updated_at,user_id,organization_id,role_id,status
                   ) VALUES(?,?,?,?,?,'active')""",
                (ts, ts, self.user_id, org['id'], role['id']),
            )
            conn.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def set_role(self, role):
        ok, _, _ = tenant_memberships.set_membership_role(
            self.user_id, 'solutions', role
        )
        self.assertTrue(ok)

    def test_owner_and_admin_can_administer_and_manage(self):
        for role in ('owner', 'admin'):
            with self.subTest(role=role):
                self.set_role(role)
                access = crm_auth.access_for(self.user_id, 'solutions')
                self.assertTrue(access.can_view)
                self.assertTrue(access.can_manage)
                self.assertTrue(access.can_administer)
                self.assertTrue(
                    crm_auth.can(self.user_id, 'solutions', 'crm_admin')
                )

    def test_staff_can_manage_but_not_administer(self):
        self.set_role('staff')
        access = crm_auth.access_for(self.user_id, 'solutions')
        self.assertTrue(access.can_view)
        self.assertTrue(access.can_manage)
        self.assertFalse(access.can_administer)
        for capability in (
            'companies', 'contacts', 'opportunities', 'tasks',
            'activities', 'conversation_links', 'quotes'
        ):
            self.assertTrue(
                crm_auth.can(self.user_id, 'solutions', capability)
            )
        self.assertFalse(crm_auth.can(self.user_id, 'solutions', 'crm_admin'))

    def test_viewer_is_read_only(self):
        self.set_role('viewer')
        access = crm_auth.access_for(self.user_id, 'solutions')
        self.assertTrue(access.can_view)
        self.assertFalse(access.can_manage)
        self.assertFalse(access.can_administer)
        self.assertTrue(crm_auth.can(self.user_id, 'solutions', 'view'))
        with self.assertRaises(PermissionError):
            crm_admin.create_company(
                self.user_id, 'solutions', name='Blocked'
            )

    def test_management_facade_enforces_membership_and_tenant(self):
        self.set_role('staff')
        company = crm_admin.create_company(
            self.user_id, 'solutions', name='Managed Co'
        )
        self.assertEqual('Managed Co', company.name)
        summary = crm_admin.summary_for(self.user_id, 'solutions')
        self.assertEqual(1, summary.companies)
        with self.assertRaises(PermissionError):
            crm_admin.create_company(
                self.user_id, 'adventures', name='Cross tenant'
            )

    def test_revoked_membership_loses_all_crm_access(self):
        self.set_role('admin')
        tenant_memberships.revoke_membership(self.user_id, 'solutions')
        self.assertIsNone(crm_auth.access_for(self.user_id, 'solutions'))
        self.assertFalse(crm_auth.can(self.user_id, 'solutions', 'view'))
        with self.assertRaises(PermissionError):
            crm_admin.summary_for(self.user_id, 'solutions')

    def test_unknown_capability_fails_closed(self):
        self.set_role('owner')
        self.assertFalse(crm_auth.can(self.user_id, 'solutions', 'billing'))

    def test_platform_admin_identity_is_not_a_crm_membership_shortcut(self):
        # CRM access accepts only a tenant user id with an active membership.
        # A bootstrap/platform admin session has no membership-derived user id.
        self.assertFalse(crm_auth.can(999999, 'solutions', 'crm_admin'))
        with self.assertRaises(PermissionError):
            crm_admin.summary_for(999999, 'solutions')


if __name__ == '__main__':
    unittest.main()
