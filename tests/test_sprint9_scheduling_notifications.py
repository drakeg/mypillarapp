from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import portal_notifications
import portal_tenancy
import scheduling_admin
import scheduling_appointments
import scheduling_availability
import scheduling_calendars
import scheduling_customer
import scheduling_notifications
import scheduling_public_booking
import tenant_auth
import tenant_sites


def epoch(year, month, day, hour=0, minute=0):
    return int(
        datetime(
            year, month, day, hour, minute, tzinfo=timezone.utc
        ).timestamp()
    )


class Sprint9SchedulingNotificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()
        scheduling_notifications.ensure_schema()

        self.owner = self._user(
            'solutions', 'owner@example.com', 'owner'
        )
        self.staff = self._user(
            'solutions', 'staff@example.com', 'staff'
        )
        self.customer = self._user(
            'solutions', 'jane@example.com', 'viewer'
        )
        self.scope = self._scope(
            self.customer, 'solutions', 'jane@example.com'
        )

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
        self.resource = scheduling_availability.create_resource(
            'solutions',
            self.calendar.id,
            slug='room',
            name='Room',
            kind='room',
        )
        scheduling_availability.assign_service_resource(
            'solutions',
            service_id=self.service.id,
            resource_id=self.resource.id,
        )
        scheduling_availability.add_weekly_availability(
            'solutions',
            self.resource.id,
            weekday=0,
            start_minute=9 * 60,
            end_minute=17 * 60,
        )
        self.now = epoch(2026, 11, 22, 7)
        self.start = epoch(2026, 11, 23, 9)

    def tearDown(self):
        self.tmp.cleanup()

    def test_guest_public_booking_schedules_email_metadata_only(self):
        booking = scheduling_public_booking.create_public_booking(
            'solutions',
            'main',
            calendar_slug='consulting',
            service_slug='consultation',
            start_at=self.start,
            guest_name='Jane Guest',
            guest_email='jane@example.com',
            now=self.now,
        )
        appointment = next(
            row for row in scheduling_appointments.list_appointments(
                'solutions'
            )
            if row.public_ref == booking.reference
        )
        rows = scheduling_notifications.list_notifications(
            'solutions', appointment.id
        )
        self.assertEqual(
            ['confirmation', 'reminder', 'reminder'],
            [row.kind for row in rows],
        )
        self.assertEqual(
            ['email', 'email', 'email'],
            [row.channel for row in rows],
        )

        due = scheduling_notifications.list_due_guest_email(
            'solutions',
            now=self.now,
        )
        self.assertEqual(1, len(due))
        self.assertEqual('confirmation', due[0].kind)
        self.assertEqual('jane@example.com', due[0].guest_email)
        self.assertNotIn('Room', due[0].body)
        self.assertNotIn('resource', due[0].body.lower())

        deliveries = portal_notifications.list_deliveries(
            'solutions',
            customer_user_id=self.customer,
        )
        self.assertEqual([], deliveries)

    def test_guest_adapter_must_explicitly_mark_due_email_queued(self):
        booking = scheduling_public_booking.create_public_booking(
            'solutions',
            'main',
            calendar_slug='consulting',
            service_slug='consultation',
            start_at=self.start,
            guest_name='Jane Guest',
            guest_email='jane@example.com',
            now=self.now,
        )
        appointment = next(
            row for row in scheduling_appointments.list_appointments(
                'solutions'
            )
            if row.public_ref == booking.reference
        )
        due = scheduling_notifications.list_due_guest_email(
            'solutions',
            now=self.now,
        )[0]
        queued = scheduling_notifications.mark_guest_email_queued(
            'solutions', due.notification_id
        )
        self.assertEqual('queued', queued.status)
        rows = scheduling_notifications.list_notifications(
            'solutions', appointment.id
        )
        self.assertEqual('queued', rows[0].status)

    def test_authenticated_customer_due_notices_use_portal_queue(self):
        appointment = scheduling_admin.create_appointment(
            self.staff,
            'solutions',
            service_id=self.service.id,
            resource_id=self.resource.id,
            start_at=self.start,
            customer_user_id=self.customer,
            status='confirmed',
        )
        processed = scheduling_notifications.queue_due_authenticated(
            'solutions',
            now=tenant_auth.now(),
        )
        self.assertEqual(2, len(processed))
        self.assertTrue(
            all(row.status == 'queued' for row in processed)
        )

        deliveries = portal_notifications.list_deliveries(
            'solutions',
            customer_user_id=self.customer,
        )
        self.assertEqual(2, len(deliveries))
        self.assertEqual(
            {'email', 'in_app'},
            {row.channel for row in deliveries},
        )
        self.assertTrue(
            all(
                row.notification_type == 'service_notice'
                for row in deliveries
            )
        )
        self.assertTrue(
            all(
                'Consultation' in row.subject
                for row in deliveries
            )
        )
        self.assertEqual(
            appointment.id,
            scheduling_notifications.list_notifications(
                'solutions', appointment.id
            )[0].appointment_id,
        )

    def test_portal_preference_can_suppress_authenticated_email(self):
        portal_notifications.set_preference(
            'solutions',
            customer_user_id=self.customer,
            channel='email',
            notification_type='service_notice',
            enabled=False,
        )
        appointment = scheduling_admin.create_appointment(
            self.staff,
            'solutions',
            service_id=self.service.id,
            resource_id=self.resource.id,
            start_at=self.start,
            customer_user_id=self.customer,
        )
        processed = scheduling_notifications.queue_due_authenticated(
            'solutions',
            now=tenant_auth.now(),
        )
        by_channel = {
            row.channel: row.status for row in processed
        }
        self.assertEqual('suppressed', by_channel['email'])
        self.assertEqual('queued', by_channel['in_app'])

        deliveries = portal_notifications.list_deliveries(
            'solutions',
            customer_user_id=self.customer,
        )
        self.assertEqual(['in_app'], [row.channel for row in deliveries])
        self.assertEqual(
            appointment.id,
            processed[0].appointment_id,
        )

    def test_cancellation_cancels_still_scheduled_notifications(self):
        appointment = scheduling_admin.create_appointment(
            self.staff,
            'solutions',
            service_id=self.service.id,
            resource_id=self.resource.id,
            start_at=self.start,
            customer_user_id=self.customer,
        )
        scheduling_admin.transition_appointment(
            self.staff,
            'solutions',
            appointment.id,
            to_status='canceled',
        )
        rows = scheduling_notifications.list_notifications(
            'solutions', appointment.id
        )
        self.assertTrue(rows)
        self.assertTrue(
            all(row.status == 'canceled' for row in rows)
        )

    def test_customer_reschedule_rebuilds_future_reminders(self):
        booking = scheduling_public_booking.create_public_booking(
            'solutions',
            'main',
            calendar_slug='consulting',
            service_slug='consultation',
            start_at=self.start,
            guest_name='Jane Guest',
            guest_email='jane@example.com',
            now=self.now,
        )
        appointment = next(
            row for row in scheduling_appointments.list_appointments(
                'solutions'
            )
            if row.public_ref == booking.reference
        )
        scheduling_customer.claim_matching_guest_bookings(self.scope)
        new_start = epoch(2026, 11, 23, 11)
        updated = scheduling_customer.reschedule_customer_appointment(
            self.scope,
            appointment.id,
            start_at=new_start,
            now=self.now,
        )
        self.assertEqual(new_start, updated.start_at)

        rows = scheduling_notifications.list_notifications(
            'solutions', appointment.id
        )
        reminders = [
            row for row in rows if row.kind == 'reminder'
        ]
        scheduled = [
            row for row in reminders if row.status == 'scheduled'
        ]
        canceled = [
            row for row in reminders if row.status == 'canceled'
        ]
        self.assertTrue(scheduled)
        self.assertTrue(canceled)
        self.assertEqual(
            {'email', 'in_app'},
            {row.channel for row in scheduled},
        )

    def test_notification_schema_contains_no_provider_secrets(self):
        with tenant_auth.db() as conn:
            columns = {
                str(row['name']).lower()
                for row in conn.execute(
                    'PRAGMA table_info(scheduling_appointment_notifications)'
                ).fetchall()
            }
        prohibited = {
            'api_key',
            'secret_key',
            'webhook_secret',
            'provider_token',
            'smtp_password',
        }
        self.assertTrue(columns.isdisjoint(prohibited))

    def _scope(self, user_id, org_slug, email):
        with tenant_auth.db() as conn:
            org = conn.execute(
                'SELECT id FROM auth_organizations WHERE slug=?',
                (org_slug,),
            ).fetchone()
        return portal_tenancy.CustomerScope(
            user_id=user_id,
            organization_id=int(org['id']),
            organization_slug=org_slug,
            email=email,
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
                    now, now, org['id'], email, 'Notify', 'User',
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
