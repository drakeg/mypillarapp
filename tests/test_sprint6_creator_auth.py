from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS=Path(__file__).resolve().parents[1]/'site'/'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0,str(SOLUTIONS))

import creator_admin
import creator_auth
import server
import tenant_auth
import tenant_memberships
import tenant_sites


class Sprint6CreatorAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        data=Path(self.tmp.name)
        tenant_auth.DATA_DIR=data
        tenant_auth.DB_PATH=data/'madmallard.sqlite3'
        tenant_sites.ensure_schema()
        self.users={
            role:self._user(f'{role}@example.com',role)
            for role in ('owner','admin','staff','viewer')
        }

    def tearDown(self):
        self.tmp.cleanup()

    def _user(self,email,role):
        with tenant_auth.db() as conn:
            org=conn.execute(
                "SELECT id FROM auth_organizations WHERE slug='solutions'"
            ).fetchone()
            role_row=conn.execute(
                'SELECT id FROM auth_roles WHERE slug=?',(role,)
            ).fetchone()
            now=tenant_auth.now()
            cur=conn.execute(
                '''INSERT INTO auth_users(
                       created_at,updated_at,organization_id,email,
                       first_name,last_name,password_hash,role,is_active
                   ) VALUES(?,?,?,?,?,?,?,?,1)''',
                (
                    now,now,org['id'],email,role.title(),'User',
                    tenant_auth.hash_password('abcdefghijkl'),role,
                ),
            )
            user_id=int(cur.lastrowid)
            conn.execute(
                '''INSERT INTO auth_memberships(
                       created_at,updated_at,user_id,organization_id,
                       role_id,status
                   ) VALUES(?,?,?,?,?,'active')''',
                (now,now,user_id,org['id'],role_row['id']),
            )
            conn.commit()
        return user_id

    def test_role_matrix_matches_least_privilege(self):
        self.assertTrue(
            creator_auth.can(self.users['owner'],'solutions','creator_admin')
        )
        self.assertTrue(
            creator_auth.can(self.users['admin'],'solutions','creator_admin')
        )
        self.assertTrue(
            creator_auth.can(self.users['staff'],'solutions','products')
        )
        self.assertFalse(
            creator_auth.can(self.users['staff'],'solutions','creator_admin')
        )
        self.assertTrue(
            creator_auth.can(self.users['viewer'],'solutions','view')
        )
        self.assertTrue(
            creator_auth.can(self.users['viewer'],'solutions','analytics')
        )
        self.assertFalse(
            creator_auth.can(self.users['viewer'],'solutions','links')
        )
        self.assertFalse(
            creator_auth.can(self.users['viewer'],'solutions','unknown')
        )

    def test_staff_can_manage_content_through_admin_facade(self):
        profile=creator_admin.upsert_profile(
            self.users['staff'],'solutions','main',
            display_name='Creator',status='draft'
        )
        link=creator_admin.create_link(
            self.users['staff'],'solutions','main',
            label='Home',target='/'
        )
        self.assertEqual('Creator',profile.display_name)
        self.assertEqual('Home',link.label)

    def test_viewer_cannot_mutate_through_admin_facade(self):
        with self.assertRaises(PermissionError):
            creator_admin.create_link(
                self.users['viewer'],'solutions','main',
                label='Nope',target='/nope'
            )

    def test_staff_cannot_use_creator_admin_capability(self):
        with self.assertRaises(PermissionError):
            creator_admin.require_administration(
                self.users['staff'],'solutions','main'
            )
        creator_admin.require_administration(
            self.users['owner'],'solutions','main'
        )

    def test_revoked_membership_fails_closed(self):
        tenant_memberships.revoke_membership(
            self.users['staff'],'solutions'
        )
        self.assertIsNone(
            creator_auth.access_for(self.users['staff'],'solutions')
        )
        with self.assertRaises(PermissionError):
            creator_admin.create_link(
                self.users['staff'],'solutions','main',
                label='Nope',target='/nope'
            )

    def test_disabled_user_fails_closed_even_with_active_membership(self):
        with tenant_auth.db() as conn:
            conn.execute(
                'UPDATE auth_users SET is_active=0 WHERE id=?',
                (self.users['staff'],),
            )
            conn.commit()
        self.assertFalse(
            creator_auth.can(
                self.users['staff'],'solutions','links'
            )
        )

    def test_suspended_organization_fails_closed(self):
        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_organizations SET status='suspended' "
                "WHERE slug='solutions'"
            )
            conn.commit()
        self.assertFalse(
            creator_auth.can(
                self.users['owner'],'solutions','creator_admin'
            )
        )

    def test_cross_tenant_membership_does_not_grant_access(self):
        tenant_memberships.grant_membership(
            self.users['staff'],'personal-training','staff'
        )
        self.assertTrue(
            creator_auth.can(
                self.users['staff'],'personal-training','links'
            )
        )
        # A Solutions membership does not authorize mutation through another
        # tenant unless that independent membership exists.
        tenant_memberships.revoke_membership(
            self.users['staff'],'personal-training'
        )
        with self.assertRaises(PermissionError):
            creator_admin.create_link(
                self.users['staff'],'personal-training','main',
                label='Nope',target='/nope'
            )

    def test_platform_admin_identity_has_no_implicit_tenant_access(self):
        original=(
            server.ADMIN_USERNAME,
            server.ADMIN_PASSWORD_HASH,
            server.ADMIN_SESSION_SECRET,
        )
        try:
            server.ADMIN_USERNAME='platform-admin'
            server.ADMIN_PASSWORD_HASH='configured'
            server.ADMIN_SESSION_SECRET='test-platform-secret'
            token=server.make_admin_session('platform-admin')
            self.assertTrue(
                server.verify_admin_session(
                    token,
                    server.PLATFORM_ADMIN_SCOPE,
                )
            )
            # Platform administration is a separate authenticated scope, not
            # a tenant auth_users identity or membership. Having a valid
            # platform session therefore cannot satisfy creator tenant RBAC.
            self.assertFalse(
                creator_auth.can(999999,'solutions','creator_admin')
            )
        finally:
            (
                server.ADMIN_USERNAME,
                server.ADMIN_PASSWORD_HASH,
                server.ADMIN_SESSION_SECRET,
            )=original

    def test_archived_site_denies_mutation_and_read_facade(self):
        tenant_sites.create_site(
            'solutions',slug='seasonal',name='Seasonal'
        )
        tenant_sites.archive_site('solutions','seasonal')
        self.assertFalse(
            creator_auth.can_site(
                self.users['owner'],'solutions','seasonal','view'
            )
        )
        with self.assertRaises(PermissionError):
            creator_admin.summary(
                self.users['owner'],'solutions','seasonal'
            )


if __name__=='__main__':
    unittest.main()
