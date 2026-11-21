from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import scheduling_availability
import scheduling_calendars
import tenant_auth
import tenant_sites


class Sprint9SchedulingAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()
        scheduling_availability.ensure_schema()

        self.owner = self._user(
            'solutions', 'owner@example.com', 'owner'
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

        self.calendar = scheduling_calendars.create_calendar(
            'solutions',
            slug='consulting',
            name='Consulting',
            timezone_name='America/New_York',
            status='published',
        )
        self.service = scheduling_calendars.create_service_type(
            'solutions',
            self.calendar.id,
            slug='consultation',
            name='Consultation',
            duration_minutes=60,
            status='published',
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
                    now, now, org['id'], email, 'Calendar', 'User',
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

    def test_staff_resource_requires_active_same_tenant_staff_user(self):
        resource = scheduling_availability.create_resource(
            'solutions',
            self.calendar.id,
            slug='greg',
            name='Greg',
            kind='staff',
            user_id=self.staff,
        )
        self.assertEqual(self.staff, resource.user_id)
        self.assertEqual('staff', resource.kind)

        with self.assertRaises(PermissionError):
            scheduling_availability.create_resource(
                'solutions',
                self.calendar.id,
                slug='foreign',
                name='Foreign',
                kind='staff',
                user_id=self.other,
            )
        with self.assertRaises(PermissionError):
            scheduling_availability.create_resource(
                'solutions',
                self.calendar.id,
                slug='viewer',
                name='Viewer',
                kind='staff',
                user_id=self.viewer,
            )

    def test_non_staff_resource_must_not_reference_user(self):
        room = scheduling_availability.create_resource(
            'solutions',
            self.calendar.id,
            slug='conference-room',
            name='Conference Room',
            kind='room',
        )
        self.assertIsNone(room.user_id)

        with self.assertRaises(ValueError):
            scheduling_availability.create_resource(
                'solutions',
                self.calendar.id,
                slug='bad-room',
                name='Bad Room',
                kind='room',
                user_id=self.staff,
            )

    def test_resource_is_calendar_and_tenant_scoped(self):
        resource = scheduling_availability.create_resource(
            'solutions',
            self.calendar.id,
            slug='greg',
            name='Greg',
            kind='staff',
            user_id=self.staff,
        )
        self.assertIsNone(
            scheduling_availability.get_resource(
                'adventures', resource.id
            )
        )
        foreign_calendar = scheduling_calendars.create_calendar(
            'adventures',
            slug='foreign',
            name='Foreign',
            timezone_name='UTC',
        )
        with self.assertRaises(PermissionError):
            scheduling_availability.create_resource(
                'solutions',
                foreign_calendar.id,
                slug='wrong',
                name='Wrong',
                kind='staff',
                user_id=self.staff,
            )

    def test_weekly_availability_rejects_overlaps(self):
        resource = scheduling_availability.create_resource(
            'solutions',
            self.calendar.id,
            slug='greg',
            name='Greg',
            kind='staff',
            user_id=self.staff,
        )
        first = scheduling_availability.add_weekly_availability(
            'solutions',
            resource.id,
            weekday=0,
            start_minute=9 * 60,
            end_minute=12 * 60,
        )
        second = scheduling_availability.add_weekly_availability(
            'solutions',
            resource.id,
            weekday=0,
            start_minute=13 * 60,
            end_minute=17 * 60,
        )
        self.assertEqual(
            [first.id, second.id],
            [
                row.id
                for row in scheduling_availability.list_weekly_availability(
                    'solutions', resource.id
                )
            ],
        )
        with self.assertRaises(ValueError):
            scheduling_availability.add_weekly_availability(
                'solutions',
                resource.id,
                weekday=0,
                start_minute=11 * 60,
                end_minute=14 * 60,
            )

    def test_weekly_availability_validates_day_and_minutes(self):
        resource = scheduling_availability.create_resource(
            'solutions',
            self.calendar.id,
            slug='greg',
            name='Greg',
            kind='staff',
            user_id=self.staff,
        )
        with self.assertRaises(ValueError):
            scheduling_availability.add_weekly_availability(
                'solutions',
                resource.id,
                weekday=7,
                start_minute=540,
                end_minute=600,
            )
        with self.assertRaises(ValueError):
            scheduling_availability.add_weekly_availability(
                'solutions',
                resource.id,
                weekday=1,
                start_minute=600,
                end_minute=600,
            )

    def test_blackouts_use_utc_ranges_and_window_filtering(self):
        resource = scheduling_availability.create_resource(
            'solutions',
            self.calendar.id,
            slug='greg',
            name='Greg',
            kind='staff',
            user_id=self.staff,
        )
        first = scheduling_availability.add_blackout(
            'solutions',
            resource.id,
            start_at=1000,
            end_at=2000,
            reason='Vacation',
        )
        scheduling_availability.add_blackout(
            'solutions',
            resource.id,
            start_at=3000,
            end_at=4000,
            reason='Training',
        )
        rows = scheduling_availability.list_blackouts(
            'solutions',
            resource.id,
            start_at=1500,
            end_at=2500,
        )
        self.assertEqual([first.id], [row.id for row in rows])
        with self.assertRaises(ValueError):
            scheduling_availability.add_blackout(
                'solutions',
                resource.id,
                start_at=2000,
                end_at=1000,
            )

    def test_service_resource_assignment_requires_same_calendar(self):
        resource = scheduling_availability.create_resource(
            'solutions',
            self.calendar.id,
            slug='greg',
            name='Greg',
            kind='staff',
            user_id=self.staff,
        )
        scheduling_availability.assign_service_resource(
            'solutions',
            service_id=self.service.id,
            resource_id=resource.id,
        )
        rows = scheduling_availability.list_service_resources(
            'solutions', self.service.id
        )
        self.assertEqual([resource.id], [row.id for row in rows])

        other_calendar = scheduling_calendars.create_calendar(
            'solutions',
            slug='other',
            name='Other',
            timezone_name='UTC',
        )
        other_resource = scheduling_availability.create_resource(
            'solutions',
            other_calendar.id,
            slug='room',
            name='Room',
            kind='room',
        )
        with self.assertRaises(PermissionError):
            scheduling_availability.assign_service_resource(
                'solutions',
                service_id=self.service.id,
                resource_id=other_resource.id,
            )

    def test_archived_resource_cannot_receive_new_availability_or_mapping(self):
        resource = scheduling_availability.create_resource(
            'solutions',
            self.calendar.id,
            slug='greg',
            name='Greg',
            kind='staff',
            user_id=self.staff,
        )
        archived = scheduling_availability.archive_resource(
            'solutions', resource.id
        )
        self.assertEqual('archived', archived.status)
        with self.assertRaises(PermissionError):
            scheduling_availability.add_weekly_availability(
                'solutions',
                resource.id,
                weekday=0,
                start_minute=540,
                end_minute=600,
            )
        with self.assertRaises(PermissionError):
            scheduling_availability.assign_service_resource(
                'solutions',
                service_id=self.service.id,
                resource_id=resource.id,
            )


if __name__ == '__main__':
    unittest.main()
