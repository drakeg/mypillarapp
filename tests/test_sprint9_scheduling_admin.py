from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import scheduling_admin
import scheduling_availability
import scheduling_calendars
import tenant_auth
import tenant_sites


class Sprint9SchedulingAdminTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

        self.owner = self._user(
            'solutions', 'owner@example.com', 'owner'
        )
        self.admin = self._user(
            'solutions', 'admin@example.com', 'admin'
        )
        self.staff = self._user(
            'solutions', 'staff@example.com', 'staff'
        )
        self.viewer = self._user(
            'solutions', 'viewer@example.com', 'viewer'
        )
        self.other = self._user(
            'adventures', 'other@example.com', 'owner'
        )

        self.calendar = scheduling_admin.create_calendar(
            self.owner,
            'solutions',
            slug='consulting',
            name='Consulting',
            timezone_name='UTC',
        )
        self.service = scheduling_admin.create_service_type(
            self.admin,
            'solutions',
            self.calendar.id,
            slug='consultation',
            name='Consultation',
            duration_minutes=60,
        )
        self.resource = scheduling_admin.create_resource(
            self.owner,
            'solutions',
            self.calendar.id,
            slug='staff',
            name='Staff',
            kind='staff',
            user_id=self.staff,
        )
        scheduling_admin.assign_service_resource(
            self.admin,
            'solutions',
            service_id=self.service.id,
            resource_id=self.resource.id,
        )

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
                    now, now, org['id'], email, 'Schedule', 'Admin',
                    tenant_auth.hash_password('abcdefghijkl'), role,
                ),
            )
            uid = int(cur.lastrowid)
            conn.execute(
                '''INSERT INTO auth_memberships(
                       created_at,updated_at,user_id,organization_id,
                       role_id,status
                   ) VALUES(?,?,?,?,?,'active')''',
                (now, now, uid, org['id'], role_row['id']),
            )
            conn.commit()
        return uid

    def test_viewer_can_read_overview_but_cannot_mutate(self):
        overview = scheduling_admin.overview(
            self.viewer,
            'solutions',
            calendar_id=self.calendar.id,
        )
        self.assertEqual('solutions', overview.organization_slug)
        self.assertEqual([self.calendar.id], [x.id for x in overview.calendars])
        self.assertEqual([self.service.id], [x.id for x in overview.services])
        self.assertEqual([self.resource.id], [x.id for x in overview.resources])

        with self.assertRaises(PermissionError):
            scheduling_admin.create_appointment(
                self.viewer,
                'solutions',
                service_id=self.service.id,
                resource_id=self.resource.id,
                start_at=10_000,
            )
        with self.assertRaises(PermissionError):
            scheduling_admin.add_blackout(
                self.viewer,
                'solutions',
                self.resource.id,
                start_at=20_000,
                end_at=21_000,
            )

    def test_staff_can_manage_appointments_but_not_configuration(self):
        appointment = scheduling_admin.create_appointment(
            self.staff,
            'solutions',
            service_id=self.service.id,
            resource_id=self.resource.id,
            start_at=10_000,
            status='pending',
        )
        self.assertEqual(self.staff, appointment.created_by_user_id)

        confirmed = scheduling_admin.transition_appointment(
            self.staff,
            'solutions',
            appointment.id,
            to_status='confirmed',
            reason='Confirmed by staff',
        )
        self.assertEqual('confirmed', confirmed.status)

        with self.assertRaises(PermissionError):
            scheduling_admin.create_calendar(
                self.staff,
                'solutions',
                slug='forbidden',
                name='Forbidden',
                timezone_name='UTC',
            )
        with self.assertRaises(PermissionError):
            scheduling_admin.create_resource(
                self.staff,
                'solutions',
                self.calendar.id,
                slug='forbidden',
                name='Forbidden',
                kind='room',
            )

    def test_owner_admin_can_manage_configuration(self):
        availability = scheduling_admin.add_weekly_availability(
            self.owner,
            'solutions',
            self.resource.id,
            weekday=0,
            start_minute=540,
            end_minute=1020,
        )
        self.assertEqual(0, availability.weekday)

        blackout = scheduling_admin.add_blackout(
            self.admin,
            'solutions',
            self.resource.id,
            start_at=20_000,
            end_at=21_000,
            reason='Unavailable',
        )
        self.assertEqual('Unavailable', blackout.reason)

        updated = scheduling_admin.update_calendar(
            self.admin,
            'solutions',
            self.calendar.id,
            minimum_notice_minutes=120,
        )
        self.assertEqual(120, updated.minimum_notice_minutes)

    def test_cross_tenant_overview_and_mutation_fail_closed(self):
        with self.assertRaises(PermissionError):
            scheduling_admin.overview(
                self.other,
                'solutions',
                calendar_id=self.calendar.id,
            )
        with self.assertRaises(PermissionError):
            scheduling_admin.create_appointment(
                self.other,
                'solutions',
                service_id=self.service.id,
                resource_id=self.resource.id,
                start_at=10_000,
            )

    def test_overview_filters_appointments_to_selected_calendar(self):
        first = scheduling_admin.create_appointment(
            self.staff,
            'solutions',
            service_id=self.service.id,
            resource_id=self.resource.id,
            start_at=10_000,
        )
        other_calendar = scheduling_admin.create_calendar(
            self.owner,
            'solutions',
            slug='other',
            name='Other',
            timezone_name='UTC',
        )
        other_service = scheduling_admin.create_service_type(
            self.owner,
            'solutions',
            other_calendar.id,
            slug='other',
            name='Other',
            duration_minutes=30,
        )
        other_resource = scheduling_admin.create_resource(
            self.owner,
            'solutions',
            other_calendar.id,
            slug='room',
            name='Room',
            kind='room',
        )
        scheduling_admin.assign_service_resource(
            self.owner,
            'solutions',
            service_id=other_service.id,
            resource_id=other_resource.id,
        )
        scheduling_admin.create_appointment(
            self.staff,
            'solutions',
            service_id=other_service.id,
            resource_id=other_resource.id,
            start_at=20_000,
        )

        overview = scheduling_admin.overview(
            self.viewer,
            'solutions',
            calendar_id=self.calendar.id,
        )
        self.assertEqual(
            [first.id],
            [item.id for item in overview.appointments],
        )

    def test_unknown_calendar_is_not_probeable(self):
        with self.assertRaises(PermissionError):
            scheduling_admin.overview(
                self.viewer,
                'solutions',
                calendar_id=999999,
            )


if __name__ == '__main__':
    unittest.main()
