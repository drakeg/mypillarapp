from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import portal_admin
import portal_auth
import portal_files
import portal_projects
import portal_tenancy
import portal_tickets
import tenant_auth
import tenant_memberships


class Sprint5PortalAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        with tenant_auth.db() as conn:
            org = conn.execute(
                "SELECT id FROM auth_organizations WHERE slug='solutions'"
            ).fetchone()
            viewer = conn.execute(
                "SELECT id FROM auth_roles WHERE slug='viewer'"
            ).fetchone()
            ts = tenant_auth.now()
            staff = conn.execute(
                """INSERT INTO auth_users(
                       created_at,updated_at,organization_id,email,
                       first_name,last_name,password_hash,role,is_active
                   ) VALUES(?,?,?,?,?,?,?,?,1)""",
                (
                    ts, ts, org['id'], 'portal-staff@example.com',
                    'Portal', 'Staff',
                    tenant_auth.hash_password('abcdefghijkl'),
                    'viewer',
                ),
            )
            self.staff_user_id = int(staff.lastrowid)
            conn.execute(
                """INSERT INTO auth_memberships(
                       created_at,updated_at,user_id,organization_id,
                       role_id,status
                   ) VALUES(?,?,?,?,?,'active')""",
                (
                    ts, ts, self.staff_user_id,
                    org['id'], viewer['id'],
                ),
            )
            customer = conn.execute(
                """INSERT INTO auth_users(
                       created_at,updated_at,organization_id,email,
                       first_name,last_name,password_hash,role,is_active
                   ) VALUES(?,?,?,?,?,?,?,?,1)""",
                (
                    ts, ts, org['id'], 'customer@example.com',
                    'Customer', 'One',
                    tenant_auth.hash_password('abcdefghijkl'),
                    'viewer',
                ),
            )
            self.customer_id = int(customer.lastrowid)
            conn.execute(
                """INSERT INTO auth_memberships(
                       created_at,updated_at,user_id,organization_id,
                       role_id,status
                   ) VALUES(?,?,?,?,?,'active')""",
                (
                    ts, ts, self.customer_id,
                    org['id'], viewer['id'],
                ),
            )
            other = conn.execute(
                """INSERT INTO auth_users(
                       created_at,updated_at,organization_id,email,
                       first_name,last_name,password_hash,role,is_active
                   ) VALUES(?,?,?,?,?,?,?,?,1)""",
                (
                    ts, ts, org['id'], 'other@example.com',
                    'Other', 'Customer',
                    tenant_auth.hash_password('abcdefghijkl'),
                    'viewer',
                ),
            )
            self.other_customer_id = int(other.lastrowid)
            conn.execute(
                """INSERT INTO auth_memberships(
                       created_at,updated_at,user_id,organization_id,
                       role_id,status
                   ) VALUES(?,?,?,?,?,'active')""",
                (
                    ts, ts, self.other_customer_id,
                    org['id'], viewer['id'],
                ),
            )
            conn.commit()

        self.scope = portal_tenancy.customer_scope({
            'id': self.customer_id,
            'organization_slug': 'solutions',
            'email': 'customer@example.com',
        })

    def tearDown(self):
        self.tmp.cleanup()

    def set_staff_role(self, role):
        ok, _, _ = tenant_memberships.set_membership_role(
            self.staff_user_id, 'solutions', role
        )
        self.assertTrue(ok)

    def test_owner_admin_staff_can_manage_portal_records(self):
        for role in ('owner', 'admin', 'staff'):
            with self.subTest(role=role):
                self.set_staff_role(role)
                access = portal_auth.staff_access_for(
                    self.staff_user_id, 'solutions'
                )
                self.assertTrue(access.can_view)
                self.assertTrue(access.can_manage)
                project = portal_admin.create_project(
                    self.staff_user_id,
                    'solutions',
                    customer_user_id=self.customer_id,
                    title=f'{role} project',
                )
                self.assertEqual(self.customer_id, project.customer_user_id)

    def test_viewer_is_read_only_and_not_portal_admin(self):
        access = portal_auth.staff_access_for(
            self.staff_user_id, 'solutions'
        )
        self.assertTrue(access.can_view)
        self.assertFalse(access.can_manage)
        self.assertFalse(access.can_administer)
        self.assertTrue(
            portal_auth.staff_can(
                self.staff_user_id, 'solutions', 'view'
            )
        )
        with self.assertRaises(PermissionError):
            portal_admin.create_project(
                self.staff_user_id,
                'solutions',
                customer_user_id=self.customer_id,
                title='Blocked',
            )

    def test_only_owner_admin_have_portal_admin_capability(self):
        self.set_staff_role('staff')
        self.assertFalse(
            portal_auth.staff_can(
                self.staff_user_id, 'solutions', 'portal_admin'
            )
        )
        for role in ('owner', 'admin'):
            self.set_staff_role(role)
            self.assertTrue(
                portal_auth.staff_can(
                    self.staff_user_id, 'solutions', 'portal_admin'
                )
            )

    def test_customer_scope_can_only_access_owned_visible_records(self):
        project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.customer_id,
            title='Mine',
        )
        other_project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.other_customer_id,
            title='Other',
        )
        ticket = portal_tickets.create_ticket(
            'solutions',
            customer_user_id=self.customer_id,
            project_id=project.id,
            subject='Visible ticket',
            visibility='customer',
        )
        internal_ticket = portal_tickets.create_ticket(
            'solutions',
            customer_user_id=self.customer_id,
            project_id=project.id,
            subject='Internal ticket',
            visibility='internal',
        )
        file = portal_files.create_file(
            'solutions',
            customer_user_id=self.customer_id,
            project_id=project.id,
            name='visible.pdf',
            source_type='storage_key',
            source='customers/visible.pdf',
            visibility='customer',
        )
        internal_file = portal_files.create_file(
            'solutions',
            customer_user_id=self.customer_id,
            project_id=project.id,
            name='internal.pdf',
            source_type='storage_key',
            source='customers/internal.pdf',
            visibility='internal',
        )

        self.assertTrue(
            portal_auth.customer_can_access_project(
                self.scope, project.id
            )
        )
        self.assertFalse(
            portal_auth.customer_can_access_project(
                self.scope, other_project.id
            )
        )
        self.assertTrue(
            portal_auth.customer_can_access_ticket(
                self.scope, ticket.id
            )
        )
        self.assertFalse(
            portal_auth.customer_can_access_ticket(
                self.scope, internal_ticket.id
            )
        )
        self.assertTrue(
            portal_auth.customer_can_access_file(
                self.scope, file.id
            )
        )
        self.assertFalse(
            portal_auth.customer_can_access_file(
                self.scope, internal_file.id
            )
        )

    def test_revoked_staff_membership_and_suspended_tenant_fail_closed(self):
        self.set_staff_role('admin')
        tenant_memberships.revoke_membership(
            self.staff_user_id, 'solutions'
        )
        self.assertIsNone(
            portal_auth.staff_access_for(
                self.staff_user_id, 'solutions'
            )
        )
        self.assertFalse(
            portal_auth.staff_can(
                self.staff_user_id, 'solutions', 'projects'
            )
        )

        self.set_staff_role('admin')
        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_organizations "
                "SET status='suspended' WHERE slug='solutions'"
            )
            conn.commit()
        self.assertIsNone(
            portal_auth.staff_access_for(
                self.staff_user_id, 'solutions'
            )
        )
        self.assertFalse(
            portal_auth.staff_can(
                self.staff_user_id, 'solutions', 'view'
            )
        )

    def test_revoked_customer_scope_fails_closed(self):
        tenant_memberships.revoke_membership(
            self.customer_id, 'solutions'
        )
        self.assertFalse(
            portal_auth.customer_can_access_project(
                self.scope, 1
            )
        )
        with self.assertRaises(PermissionError):
            portal_auth.revalidate_customer_scope(self.scope)

    def test_unknown_capability_and_platform_admin_identity_fail_closed(self):
        self.set_staff_role('owner')
        self.assertFalse(
            portal_auth.staff_can(
                self.staff_user_id, 'solutions', 'billing'
            )
        )
        self.assertFalse(
            portal_auth.staff_can(
                999999, 'solutions', 'portal_admin'
            )
        )
        with self.assertRaises(PermissionError):
            portal_admin.summary_for(999999, 'solutions')


if __name__ == '__main__':
    unittest.main()
