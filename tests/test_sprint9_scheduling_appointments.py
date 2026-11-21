from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import crm_contacts
import scheduling_appointments
import scheduling_availability
import scheduling_calendars
import tenant_auth
import tenant_sites


class Sprint9AppointmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()
        crm_contacts.ensure_schema()
        scheduling_appointments.ensure_schema()

        self.owner = self._user(
            'solutions', 'owner@example.com', 'owner'
        )
        self.staff = self._user(
            'solutions', 'staff@example.com', 'staff'
        )
        self.viewer = self._user(
            'solutions', 'customer@example.com', 'viewer'
        )
        self.other = self._user(
            'adventures', 'other@example.com', 'viewer'
        )

        self.calendar = scheduling_calendars.create_calendar(
            'solutions',
            slug='consulting',
            name='Consulting',
            timezone_name='UTC',
            status='published',
        )
        self.service = scheduling_calendars.create_service_type(
            'solutions',
            self.calendar.id,
            slug='consultation',
            name='Consultation',
            duration_minutes=60,
            buffer_before_minutes=15,
            buffer_after_minutes=10,
            status='published',
        )
        self.resource = scheduling_availability.create_resource(
            'solutions',
            self.calendar.id,
            slug='staff',
            name='Staff',
            kind='staff',
            user_id=self.staff,
        )
        scheduling_availability.assign_service_resource(
            'solutions',
            service_id=self.service.id,
            resource_id=self.resource.id,
        )
        self.contact = crm_contacts.create_contact(
            'solutions',
            name='Customer',
            email='customer@example.com',
            status='customer',
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
                    now, now, org['id'], email, 'Appointment', 'User',
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

    def _create(self, *, start_at=10_000, status='confirmed'):
        return scheduling_appointments.create_appointment(
            'solutions',
            service_id=self.service.id,
            resource_id=self.resource.id,
            start_at=start_at,
            status=status,
            customer_user_id=self.viewer,
            crm_contact_id=self.contact.id,
            actor_user_id=self.staff,
            reason='Booked by staff',
        )

    def test_appointment_snapshots_duration_and_buffers(self):
        appointment = self._create()
        self.assertEqual(10_000, appointment.start_at)
        self.assertEqual(13_600, appointment.end_at)
        self.assertEqual(9_100, appointment.block_start_at)
        self.assertEqual(14_200, appointment.block_end_at)
        self.assertEqual(60, appointment.duration_minutes)
        self.assertEqual(15, appointment.buffer_before_minutes)
        self.assertEqual(10, appointment.buffer_after_minutes)

        scheduling_calendars.update_service_type(
            'solutions',
            self.service.id,
            duration_minutes=90,
            buffer_before_minutes=0,
            buffer_after_minutes=0,
        )
        unchanged = scheduling_appointments.get_appointment(
            'solutions', appointment.id
        )
        self.assertEqual(60, unchanged.duration_minutes)
        self.assertEqual(9_100, unchanged.block_start_at)
        self.assertEqual(14_200, unchanged.block_end_at)

    def test_overlapping_buffered_booking_is_rejected(self):
        self._create(start_at=10_000)
        with self.assertRaises(ValueError):
            self._create(start_at=15_000)

        second = self._create(start_at=15_100)
        self.assertEqual(15_100, second.start_at)

    def test_canceled_appointment_releases_conflict_window(self):
        first = self._create(start_at=10_000)
        canceled = scheduling_appointments.transition_appointment(
            'solutions',
            first.id,
            to_status='canceled',
            actor_user_id=self.staff,
            reason='Customer canceled',
        )
        self.assertEqual('canceled', canceled.status)

        replacement = self._create(start_at=10_000)
        self.assertNotEqual(first.id, replacement.id)

    def test_resource_must_be_assigned_to_service(self):
        other_resource = scheduling_availability.create_resource(
            'solutions',
            self.calendar.id,
            slug='room',
            name='Room',
            kind='room',
        )
        with self.assertRaises(PermissionError):
            scheduling_appointments.create_appointment(
                'solutions',
                service_id=self.service.id,
                resource_id=other_resource.id,
                start_at=10_000,
            )

    def test_service_and_resource_must_share_calendar(self):
        other_calendar = scheduling_calendars.create_calendar(
            'solutions',
            slug='other',
            name='Other',
            timezone_name='UTC',
        )
        other_service = scheduling_calendars.create_service_type(
            'solutions',
            other_calendar.id,
            slug='other',
            name='Other',
            duration_minutes=30,
        )
        with self.assertRaises(PermissionError):
            scheduling_appointments.create_appointment(
                'solutions',
                service_id=other_service.id,
                resource_id=self.resource.id,
                start_at=10_000,
            )

    def test_cross_tenant_customer_and_contact_fail_closed(self):
        foreign_contact = crm_contacts.create_contact(
            'adventures',
            name='Foreign',
            status='customer',
        )
        with self.assertRaises(PermissionError):
            scheduling_appointments.create_appointment(
                'solutions',
                service_id=self.service.id,
                resource_id=self.resource.id,
                start_at=10_000,
                customer_user_id=self.other,
            )
        with self.assertRaises(PermissionError):
            scheduling_appointments.create_appointment(
                'solutions',
                service_id=self.service.id,
                resource_id=self.resource.id,
                start_at=10_000,
                crm_contact_id=foreign_contact.id,
            )

    def test_cross_tenant_appointment_read_is_hidden(self):
        appointment = self._create()
        self.assertIsNone(
            scheduling_appointments.get_appointment(
                'adventures', appointment.id
            )
        )

    def test_lifecycle_is_deterministic_and_append_only(self):
        appointment = self._create(status='pending')
        confirmed = scheduling_appointments.transition_appointment(
            'solutions',
            appointment.id,
            to_status='confirmed',
            actor_user_id=self.staff,
            reason='Accepted',
        )
        self.assertEqual('confirmed', confirmed.status)
        completed = scheduling_appointments.transition_appointment(
            'solutions',
            appointment.id,
            to_status='completed',
            actor_user_id=self.staff,
            reason='Delivered',
        )
        self.assertEqual('completed', completed.status)

        with self.assertRaises(ValueError):
            scheduling_appointments.transition_appointment(
                'solutions',
                appointment.id,
                to_status='confirmed',
                actor_user_id=self.staff,
            )

        transitions = scheduling_appointments.list_transitions(
            'solutions', appointment.id
        )
        self.assertEqual(
            [
                ('new', 'pending'),
                ('pending', 'confirmed'),
                ('confirmed', 'completed'),
            ],
            [
                (row.from_status, row.to_status)
                for row in transitions
            ],
        )

    def test_viewer_cannot_be_recorded_as_staff_actor(self):
        with self.assertRaises(PermissionError):
            scheduling_appointments.create_appointment(
                'solutions',
                service_id=self.service.id,
                resource_id=self.resource.id,
                start_at=10_000,
                actor_user_id=self.viewer,
            )

    def test_list_filters_customer_resource_and_time_window(self):
        first = self._create(start_at=10_000)
        second = self._create(start_at=20_000)

        by_customer = scheduling_appointments.list_appointments(
            'solutions',
            customer_user_id=self.viewer,
        )
        self.assertEqual(
            [first.id, second.id],
            [row.id for row in by_customer],
        )

        by_window = scheduling_appointments.list_appointments(
            'solutions',
            resource_id=self.resource.id,
            start_at=9_000,
            end_at=14_000,
        )
        self.assertEqual([first.id], [row.id for row in by_window])


if __name__ == '__main__':
    unittest.main()
