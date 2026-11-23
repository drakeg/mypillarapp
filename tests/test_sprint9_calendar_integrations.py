from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import scheduling_appointments
import scheduling_availability
import scheduling_calendars
import scheduling_integrations
import tenant_auth
import tenant_sites


class Sprint9CalendarIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

        self.owner = self._user('solutions', 'owner@example.com', 'owner')
        self.other = self._user('adventures', 'other@example.com', 'owner')

        self.calendar = scheduling_calendars.create_calendar(
            'solutions',
            slug='consulting',
            name='Consulting, LLC',
            timezone_name='UTC',
            status='published',
        )
        self.service = scheduling_calendars.create_service_type(
            'solutions',
            self.calendar.id,
            slug='consultation',
            name='Consultation; Review',
            duration_minutes=60,
            status='published',
        )
        self.resource = scheduling_availability.create_resource(
            'solutions',
            self.calendar.id,
            slug='room',
            name='Private Room',
            kind='room',
        )
        scheduling_availability.assign_service_resource(
            'solutions',
            service_id=self.service.id,
            resource_id=self.resource.id,
        )
        self.appointment = scheduling_appointments.create_appointment(
            'solutions',
            service_id=self.service.id,
            resource_id=self.resource.id,
            start_at=2_000_000_000,
            status='confirmed',
            guest_name='Secret Customer',
            guest_email='secret@example.com',
            guest_phone='+15551234567',
            actor_user_id=self.owner,
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

    def test_single_appointment_export_is_valid_and_private(self):
        export = scheduling_integrations.export_appointment(
            self.owner, 'solutions', self.appointment.id
        )
        self.assertEqual('text/calendar; charset=utf-8', export.content_type)
        self.assertIn('BEGIN:VCALENDAR\r\n', export.body)
        self.assertIn('BEGIN:VEVENT\r\n', export.body)
        self.assertIn('SUMMARY:Consultation\\; Review', export.body)
        self.assertIn('STATUS:CONFIRMED', export.body)
        self.assertNotIn('Secret Customer', export.body)
        self.assertNotIn('secret@example.com', export.body)
        self.assertNotIn('Private Room', export.body)

    def test_cross_tenant_export_fails_closed(self):
        with self.assertRaises(PermissionError):
            scheduling_integrations.export_appointment(
                self.other, 'solutions', self.appointment.id
            )

    def test_calendar_export_is_bounded_to_selected_calendar_and_window(self):
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
            name='Other Service',
            duration_minutes=30,
        )
        other_resource = scheduling_availability.create_resource(
            'solutions',
            other_calendar.id,
            slug='other-room',
            name='Other Room',
            kind='room',
        )
        scheduling_availability.assign_service_resource(
            'solutions',
            service_id=other_service.id,
            resource_id=other_resource.id,
        )
        scheduling_appointments.create_appointment(
            'solutions',
            service_id=other_service.id,
            resource_id=other_resource.id,
            start_at=2_000_000_000,
            actor_user_id=self.owner,
        )
        export = scheduling_integrations.export_calendar(
            self.owner,
            'solutions',
            self.calendar.id,
            start_at=1_999_990_000,
            end_at=2_000_010_000,
        )
        self.assertIn('Consultation\\; Review', export.body)
        self.assertNotIn('Other Service', export.body)

    def test_canceled_status_maps_to_ics_cancelled(self):
        scheduling_appointments.transition_appointment(
            'solutions',
            self.appointment.id,
            to_status='canceled',
            actor_user_id=self.owner,
        )
        export = scheduling_integrations.export_appointment(
            self.owner, 'solutions', self.appointment.id
        )
        self.assertIn('STATUS:CANCELLED', export.body)

    def test_external_sync_payload_contains_no_customer_or_resource_identity(self):
        payload = scheduling_integrations.sync_payload(
            'solutions', self.appointment.id
        )
        self.assertEqual('Consultation; Review', payload['summary'])
        text = repr(payload)
        self.assertNotIn('secret@example.com', text)
        self.assertNotIn('Secret Customer', text)
        self.assertNotIn('Private Room', text)

    def test_external_event_reference_is_tenant_scoped_and_bounded(self):
        event = scheduling_integrations.build_external_event(
            'solutions',
            self.appointment.id,
            provider_name='google_calendar',
            external_event_ref='provider-event-123',
        )
        self.assertEqual('google_calendar', event.provider_name)
        self.assertEqual(self.appointment.id, event.appointment_id)
        with self.assertRaises(PermissionError):
            scheduling_integrations.build_external_event(
                'adventures',
                self.appointment.id,
                provider_name='google_calendar',
                external_event_ref='provider-event-123',
            )
        with self.assertRaises(ValueError):
            scheduling_integrations.build_external_event(
                'solutions',
                self.appointment.id,
                provider_name='bad provider',
                external_event_ref='provider-event-123',
            )

    def test_export_limit_is_bounded(self):
        with self.assertRaises(ValueError):
            scheduling_integrations.export_calendar(
                self.owner,
                'solutions',
                self.calendar.id,
                start_at=1_999_990_000,
                end_at=2_000_010_000,
                limit=0,
            )


if __name__ == '__main__':
    unittest.main()
