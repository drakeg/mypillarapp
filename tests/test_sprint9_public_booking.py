from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import crm_contacts
import scheduling_appointments
import scheduling_availability
import scheduling_calendars
import scheduling_public_booking
import tenant_auth
import tenant_sites


def epoch(year, month, day, hour=0, minute=0):
    return int(
        datetime(
            year, month, day, hour, minute, tzinfo=timezone.utc
        ).timestamp()
    )


class Sprint9PublicBookingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()
        crm_contacts.ensure_schema()
        scheduling_appointments.ensure_schema()

        tenant_sites.update_site(
            'solutions', 'main', status='published'
        )
        self.site = tenant_sites.get_site('solutions', 'main')
        self.calendar = scheduling_calendars.create_calendar(
            'solutions',
            slug='consulting',
            name='Consulting',
            timezone_name='UTC',
            site_id=self.site.id,
            status='published',
            booking_horizon_days=30,
            minimum_notice_minutes=60,
        )
        self.service = scheduling_calendars.create_service_type(
            'solutions',
            self.calendar.id,
            slug='consultation',
            name='Consultation',
            duration_minutes=60,
            status='published',
        )
        self.one = scheduling_availability.create_resource(
            'solutions',
            self.calendar.id,
            slug='room-one',
            name='Room One',
            kind='room',
        )
        self.two = scheduling_availability.create_resource(
            'solutions',
            self.calendar.id,
            slug='room-two',
            name='Room Two',
            kind='room',
        )
        for resource in (self.one, self.two):
            scheduling_availability.assign_service_resource(
                'solutions',
                service_id=self.service.id,
                resource_id=resource.id,
            )
            scheduling_availability.add_weekly_availability(
                'solutions',
                resource.id,
                weekday=0,
                start_minute=9 * 60,
                end_minute=12 * 60,
            )

        self.now = epoch(2026, 11, 23, 7)
        self.start = epoch(2026, 11, 23, 9)

    def tearDown(self):
        self.tmp.cleanup()

    def _book(self, **kwargs):
        params = dict(
            organization_slug='solutions',
            site_slug='main',
            calendar_slug='consulting',
            service_slug='consultation',
            start_at=self.start,
            guest_name='Jane Customer',
            guest_email='Jane@example.com',
            guest_phone='+1 (555) 555-1212',
            now=self.now,
        )
        params.update(kwargs)
        return scheduling_public_booking.create_public_booking(
            **params
        )

    def test_public_booking_creates_confirmed_guest_snapshot(self):
        booking = self._book()
        self.assertEqual('confirmed', booking.status)
        self.assertEqual('consulting', booking.calendar_slug)
        self.assertEqual('consultation', booking.service_slug)
        self.assertEqual(self.start, booking.start_at)
        self.assertEqual(
            self.start + 3600, booking.end_at
        )
        self.assertGreaterEqual(len(booking.reference), 16)
        self.assertFalse(hasattr(booking, 'appointment_id'))
        self.assertFalse(hasattr(booking, 'resource_id'))

        appointments = scheduling_appointments.list_appointments(
            'solutions',
            start_at=self.start,
            end_at=self.start + 3601,
        )
        self.assertEqual(1, len(appointments))
        appointment = appointments[0]
        self.assertEqual(booking.reference, appointment.public_ref)
        self.assertEqual('Jane Customer', appointment.guest_name)
        self.assertEqual('jane@example.com', appointment.guest_email)
        self.assertEqual('+15555551212', appointment.guest_phone)
        self.assertIsNone(appointment.customer_user_id)
        self.assertIsNone(appointment.crm_contact_id)

    def test_public_email_does_not_auto_link_existing_identity(self):
        self._user('solutions', 'jane@example.com', 'viewer')
        crm_contacts.create_contact(
            'solutions',
            name='Jane Existing',
            email='jane@example.com',
            status='customer',
        )
        booking = self._book()
        appointment = next(
            row
            for row in scheduling_appointments.list_appointments(
                'solutions'
            )
            if row.public_ref == booking.reference
        )
        self.assertIsNone(appointment.customer_user_id)
        self.assertIsNone(appointment.crm_contact_id)

    def test_two_bookings_get_distinct_opaque_references(self):
        first = self._book()
        second = self._book(
            start_at=epoch(2026, 11, 23, 10)
        )
        self.assertNotEqual(first.reference, second.reference)

    def test_booking_uses_remaining_resource_without_exposing_it(self):
        scheduling_appointments.create_appointment(
            'solutions',
            service_id=self.service.id,
            resource_id=self.one.id,
            start_at=self.start,
        )
        booking = self._book()
        appointment = next(
            row
            for row in scheduling_appointments.list_appointments(
                'solutions'
            )
            if row.public_ref == booking.reference
        )
        self.assertEqual(self.two.id, appointment.resource_id)
        self.assertFalse(hasattr(booking, 'resource_id'))

    def test_race_conflict_on_first_resource_falls_back_to_second(self):
        original = scheduling_appointments.create_appointment
        calls = {'count': 0}

        def race_once(*args, **kwargs):
            calls['count'] += 1
            if calls['count'] == 1:
                raise scheduling_appointments.AppointmentConflictError(
                    'simulated race'
                )
            return original(*args, **kwargs)

        with mock.patch.object(
            scheduling_appointments,
            'create_appointment',
            side_effect=race_once,
        ):
            booking = self._book()
        self.assertEqual('confirmed', booking.status)
        self.assertEqual(2, calls['count'])

    def test_all_race_conflicts_fail_closed(self):
        with mock.patch.object(
            scheduling_appointments,
            'create_appointment',
            side_effect=scheduling_appointments.AppointmentConflictError(
                'simulated race'
            ),
        ):
            with self.assertRaises(
                scheduling_public_booking.PublicSlotUnavailable
            ):
                self._book()

    def test_unpublished_or_out_of_policy_slot_is_rejected(self):
        tenant_sites.update_site(
            'solutions', 'main', status='draft'
        )
        with self.assertRaises(
            scheduling_public_booking.PublicSlotUnavailable
        ):
            self._book()

        tenant_sites.update_site(
            'solutions', 'main', status='published'
        )
        with self.assertRaises(
            scheduling_public_booking.PublicSlotUnavailable
        ):
            self._book(start_at=epoch(2026, 11, 23, 7, 30))

    def test_guest_contact_fields_are_validated(self):
        with self.assertRaises(ValueError):
            self._book(guest_name='')
        with self.assertRaises(ValueError):
            self._book(guest_email='not-an-email')
        with self.assertRaises(ValueError):
            self._book(guest_phone='123')

    def test_guest_columns_and_public_reference_index_exist(self):
        with tenant_auth.db() as conn:
            columns = {
                row['name']
                for row in conn.execute(
                    'PRAGMA table_info(scheduling_appointments)'
                ).fetchall()
            }
            indexes = {
                row['name']
                for row in conn.execute(
                    'PRAGMA index_list(scheduling_appointments)'
                ).fetchall()
            }
        self.assertTrue(
            {'public_ref', 'guest_name', 'guest_email', 'guest_phone'}
            <= columns
        )
        self.assertIn(
            'idx_scheduling_appointments_public_ref', indexes
        )

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
                    now, now, org['id'], email, 'Jane', 'Existing',
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


if __name__ == '__main__':
    unittest.main()
