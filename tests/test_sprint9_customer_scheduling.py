from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import portal_tenancy
import scheduling_appointments
import scheduling_availability
import scheduling_calendars
import scheduling_customer
import scheduling_public_booking
import tenant_auth
import tenant_sites


def epoch(year, month, day, hour=0, minute=0):
    return int(
        datetime(
            year, month, day, hour, minute, tzinfo=timezone.utc
        ).timestamp()
    )


class Sprint9CustomerSchedulingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()
        scheduling_appointments.ensure_schema()

        self.customer = self._user(
            'solutions', 'jane@example.com', 'viewer'
        )
        self.other_customer = self._user(
            'solutions', 'other@example.com', 'viewer'
        )
        self.foreign_customer = self._user(
            'adventures', 'jane@example.com', 'viewer'
        )
        self.scope = self._scope(
            self.customer, 'solutions', 'jane@example.com'
        )
        self.other_scope = self._scope(
            self.other_customer, 'solutions', 'other@example.com'
        )
        self.foreign_scope = self._scope(
            self.foreign_customer, 'adventures', 'jane@example.com'
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

    def _book_guest(self, email='jane@example.com', start_at=None):
        return scheduling_public_booking.create_public_booking(
            'solutions',
            'main',
            calendar_slug='consulting',
            service_slug='consultation',
            start_at=start_at or self.start,
            guest_name='Jane Guest',
            guest_email=email,
            now=self.now,
        )

    def test_authenticated_customer_explicitly_claims_matching_guest_booking(self):
        booking = self._book_guest()
        before = scheduling_appointments.list_appointments(
            'solutions', include_canceled=True
        )[0]
        self.assertIsNone(before.customer_user_id)

        claimed = scheduling_customer.claim_matching_guest_bookings(
            self.scope
        )
        self.assertEqual(1, len(claimed))
        self.assertEqual(self.customer, claimed[0].customer_user_id)
        self.assertEqual(booking.reference, claimed[0].public_ref)

    def test_claim_does_not_cross_email_or_tenant(self):
        self._book_guest()
        self.assertEqual(
            [],
            scheduling_customer.claim_matching_guest_bookings(
                self.other_scope
            ),
        )
        self.assertEqual(
            [],
            scheduling_customer.claim_matching_guest_bookings(
                self.foreign_scope
            ),
        )

    def test_customer_list_is_ownership_scoped(self):
        self._book_guest()
        scheduling_customer.claim_matching_guest_bookings(self.scope)
        self.assertEqual(
            1,
            len(scheduling_customer.list_customer_appointments(
                self.scope
            )),
        )
        self.assertEqual(
            [],
            scheduling_customer.list_customer_appointments(
                self.other_scope
            ),
        )

    def test_customer_can_cancel_owned_booking_and_release_capacity(self):
        self._book_guest()
        appointment = scheduling_customer.claim_matching_guest_bookings(
            self.scope
        )[0]
        canceled = scheduling_customer.cancel_customer_appointment(
            self.scope, appointment.id
        )
        self.assertEqual('canceled', canceled.status)

        replacement = self._book_guest(email='other@example.com')
        self.assertEqual(self.start, replacement.start_at)

    def test_other_customer_cannot_cancel_booking(self):
        self._book_guest()
        appointment = scheduling_customer.claim_matching_guest_bookings(
            self.scope
        )[0]
        with self.assertRaises(PermissionError):
            scheduling_customer.cancel_customer_appointment(
                self.other_scope, appointment.id
            )

    def test_customer_can_reschedule_owned_booking_to_public_slot(self):
        self._book_guest()
        appointment = scheduling_customer.claim_matching_guest_bookings(
            self.scope
        )[0]
        new_start = epoch(2026, 11, 23, 10)
        updated = scheduling_customer.reschedule_customer_appointment(
            self.scope,
            appointment.id,
            start_at=new_start,
            now=self.now,
        )
        self.assertEqual(new_start, updated.start_at)
        self.assertEqual('confirmed', updated.status)

        transitions = scheduling_appointments.list_transitions(
            'solutions', appointment.id
        )
        self.assertEqual(
            'customer_rescheduled',
            transitions[-1].reason,
        )
        self.assertEqual(self.customer, transitions[-1].actor_user_id)

    def test_reschedule_can_use_second_resource_when_first_is_busy(self):
        self._book_guest()
        appointment = scheduling_customer.claim_matching_guest_bookings(
            self.scope
        )[0]
        new_start = epoch(2026, 11, 23, 10)
        scheduling_appointments.create_appointment(
            'solutions',
            service_id=self.service.id,
            resource_id=self.one.id,
            start_at=new_start,
        )

        updated = scheduling_customer.reschedule_customer_appointment(
            self.scope,
            appointment.id,
            start_at=new_start,
            now=self.now,
        )
        self.assertEqual(self.two.id, updated.resource_id)

    def test_reschedule_rejects_unpublished_or_out_of_policy_slot(self):
        self._book_guest()
        appointment = scheduling_customer.claim_matching_guest_bookings(
            self.scope
        )[0]
        scheduling_calendars.update_service_type(
            'solutions',
            self.service.id,
            status='draft',
        )
        with self.assertRaises(
            scheduling_customer.CustomerSlotUnavailable
        ):
            scheduling_customer.reschedule_customer_appointment(
                self.scope,
                appointment.id,
                start_at=epoch(2026, 11, 23, 10),
                now=self.now,
            )

    def test_completed_booking_cannot_be_canceled_or_rescheduled(self):
        self._book_guest()
        appointment = scheduling_customer.claim_matching_guest_bookings(
            self.scope
        )[0]
        scheduling_appointments.transition_appointment(
            'solutions',
            appointment.id,
            to_status='completed',
            actor_user_id=self._user(
                'solutions', 'staff@example.com', 'staff'
            ),
        )
        with self.assertRaises(ValueError):
            scheduling_customer.cancel_customer_appointment(
                self.scope, appointment.id
            )
        with self.assertRaises(ValueError):
            scheduling_customer.reschedule_customer_appointment(
                self.scope,
                appointment.id,
                start_at=epoch(2026, 11, 23, 10),
                now=self.now,
            )

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
                    now, now, org['id'], email, 'Customer', 'User',
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
