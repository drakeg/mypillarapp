from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import crm_contacts
import scheduling_boundary
import tenant_auth
import tenant_sites


class Sprint9SchedulingBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()
        crm_contacts.ensure_schema()

        self.owner = self._user('solutions', 'owner@example.com', 'owner')
        self.staff = self._user('solutions', 'staff@example.com', 'staff')
        self.viewer = self._user('solutions', 'viewer@example.com', 'viewer')
        self.other = self._user('adventures', 'other@example.com', 'owner')

    def tearDown(self):
        self.tmp.cleanup()

    def _user(self, org_slug, email, role):
        with tenant_auth.db() as conn:
            org = conn.execute(
                'SELECT id FROM auth_organizations WHERE slug=?',
                (org_slug,),
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
                    now, now, org['id'], email, 'Schedule', 'User',
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

    def test_staff_can_manage_viewer_cannot(self):
        access = scheduling_boundary.require(
            self.staff, 'solutions', 'manage'
        )
        self.assertTrue(access.can_manage)

        view = scheduling_boundary.require(
            self.viewer, 'solutions', 'view'
        )
        self.assertTrue(view.can_view)
        self.assertFalse(view.can_manage)

        with self.assertRaises(PermissionError):
            scheduling_boundary.require(
                self.viewer, 'solutions', 'manage'
            )

    def test_cross_tenant_membership_fails_closed(self):
        with self.assertRaises(PermissionError):
            scheduling_boundary.require(
                self.other, 'solutions', 'view'
            )

    def test_suspended_organization_fails_closed(self):
        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_organizations SET status='suspended' "
                "WHERE slug='solutions'"
            )
            conn.commit()
        with self.assertRaises(PermissionError):
            scheduling_boundary.require(
                self.owner, 'solutions', 'admin'
            )

    def test_timezone_validation_and_utc_round_trip(self):
        self.assertEqual(
            'America/New_York',
            scheduling_boundary.normalize_timezone(
                'America/New_York'
            ),
        )
        local = datetime(2026, 11, 21, 9, 30)
        epoch = scheduling_boundary.local_to_utc_epoch(
            local, 'America/New_York'
        )
        converted = scheduling_boundary.utc_epoch_to_local(
            epoch, 'America/New_York'
        )
        self.assertEqual(local, converted.replace(tzinfo=None))
        self.assertEqual(
            timezone.utc,
            datetime.fromtimestamp(epoch, timezone.utc).tzinfo,
        )

    def test_nonexistent_dst_local_time_is_rejected(self):
        with self.assertRaises(ValueError):
            scheduling_boundary.local_to_utc_epoch(
                datetime(2026, 3, 8, 2, 30),
                'America/New_York',
            )

    def test_invalid_timezone_is_rejected(self):
        with self.assertRaises(ValueError):
            scheduling_boundary.normalize_timezone('Mars/Olympus_Mons')

    def test_utc_range_must_be_ordered(self):
        self.assertEqual(
            (100, 200),
            scheduling_boundary.validate_utc_range(100, 200),
        )
        with self.assertRaises(ValueError):
            scheduling_boundary.validate_utc_range(200, 200)
        with self.assertRaises(ValueError):
            scheduling_boundary.validate_utc_range(201, 200)

    def test_site_reference_must_belong_to_same_tenant(self):
        own = tenant_sites.get_site('solutions', 'main')
        other = tenant_sites.get_site('adventures', 'main')
        self.assertEqual(
            own.id,
            scheduling_boundary.require_site(
                'solutions', own.id
            ),
        )
        with self.assertRaises(PermissionError):
            scheduling_boundary.require_site(
                'solutions', other.id
            )

    def test_contact_reference_must_belong_to_same_tenant(self):
        own = crm_contacts.create_contact(
            'solutions', name='Own Customer'
        )
        other = crm_contacts.create_contact(
            'adventures', name='Other Customer'
        )
        self.assertEqual(
            own.id,
            scheduling_boundary.require_contact(
                'solutions', own.id
            ),
        )
        with self.assertRaises(PermissionError):
            scheduling_boundary.require_contact(
                'solutions', other.id
            )

    def test_customer_reference_must_belong_to_same_tenant(self):
        self.assertEqual(
            self.viewer,
            scheduling_boundary.require_customer_user(
                'solutions', self.viewer
            ),
        )
        with self.assertRaises(PermissionError):
            scheduling_boundary.require_customer_user(
                'solutions', self.other
            )


if __name__ == '__main__':
    unittest.main()
