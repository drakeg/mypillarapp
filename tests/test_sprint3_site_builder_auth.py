from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import site_builder_auth
import tenant_auth
import tenant_memberships
import tenant_sites


class Sprint3SiteBuilderAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()
        with tenant_auth.db() as conn:
            org = conn.execute("SELECT id FROM auth_organizations WHERE slug='solutions'").fetchone()
            role = conn.execute("SELECT id FROM auth_roles WHERE slug='viewer'").fetchone()
            ts = tenant_auth.now()
            cur = conn.execute(
                """INSERT INTO auth_users(created_at,updated_at,organization_id,email,first_name,last_name,password_hash,role,is_active)
                   VALUES(?,?,?,?,?,?,?,?,1)""",
                (ts,ts,org['id'],'rbac@example.com','RBAC','User',tenant_auth.hash_password('abcdefghijkl'),'viewer')
            )
            self.user_id = int(cur.lastrowid)
            conn.execute(
                """INSERT INTO auth_memberships(created_at,updated_at,user_id,organization_id,role_id,status)
                   VALUES(?,?,?,?,?,'active')""",
                (ts,ts,self.user_id,org['id'],role['id'])
            )
            conn.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def set_role(self, role):
        ok, _, _ = tenant_memberships.set_membership_role(self.user_id, 'solutions', role)
        self.assertTrue(ok)

    def test_owner_and_admin_have_full_site_builder_access(self):
        for role in ('owner','admin'):
            with self.subTest(role=role):
                self.set_role(role)
                self.assertTrue(site_builder_auth.can_manage(self.user_id,'solutions','site_settings'))
                self.assertTrue(site_builder_auth.can_manage(self.user_id,'solutions','domains'))
                self.assertTrue(site_builder_auth.can_manage(self.user_id,'solutions','pages'))

    def test_staff_can_manage_content_but_not_site_or_domains(self):
        self.set_role('staff')
        for capability in ('branding','navigation','pages','services','forms','media'):
            self.assertTrue(site_builder_auth.can_manage(self.user_id,'solutions',capability))
        self.assertFalse(site_builder_auth.can_manage(self.user_id,'solutions','site_settings'))
        self.assertFalse(site_builder_auth.can_manage(self.user_id,'solutions','domains'))

    def test_viewer_has_no_site_builder_admin_access(self):
        self.set_role('viewer')
        self.assertIsNone(site_builder_auth.access_for(self.user_id,'solutions'))
        for capability in site_builder_auth.CAPABILITIES:
            self.assertFalse(site_builder_auth.can_manage(self.user_id,'solutions',capability))

    def test_access_is_organization_scoped(self):
        self.set_role('admin')
        self.assertTrue(site_builder_auth.can_manage(self.user_id,'solutions','pages'))
        self.assertFalse(site_builder_auth.can_manage(self.user_id,'personal-training','pages'))

    def test_revoked_membership_has_no_access(self):
        self.set_role('admin')
        tenant_memberships.revoke_membership(self.user_id,'solutions')
        self.assertFalse(site_builder_auth.can_manage(self.user_id,'solutions','pages'))

    def test_archived_site_cannot_be_managed(self):
        self.set_role('owner')
        tenant_sites.create_site('solutions',slug='old',name='Old')
        tenant_sites.archive_site('solutions','old')
        self.assertFalse(site_builder_auth.can_manage_site(self.user_id,'solutions','old','pages'))
        with self.assertRaises(PermissionError):
            site_builder_auth.require_site_access(self.user_id,'solutions','old','pages')

    def test_unknown_capability_is_denied(self):
        self.set_role('owner')
        self.assertFalse(site_builder_auth.can_manage(self.user_id,'solutions','billing'))


if __name__ == '__main__':
    unittest.main()
