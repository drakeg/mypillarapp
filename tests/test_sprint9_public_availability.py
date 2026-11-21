from __future__ import annotations

from datetime import datetime, timezone
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
import scheduling_public
import tenant_auth
import tenant_sites


def epoch(year, month, day, hour=0, minute=0):
    return int(
        datetime(
            year, month, day, hour, minute, tzinfo=timezone.utc
        ).timestamp()
    )


class Sprint9PublicAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()
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
            description='One hour consultation',
            duration_minutes=60,
            status='published',
        )
        self.one = scheduling_availability.create_resource(
            'solutions',
            self.calendar.id,
            slug='room-one',
            name='Private Room One',
            kind='room',
        )
        self.two = scheduling_availability.create_resource(
            'solutions',
            self.calendar.id,
            slug='room-two',
            name='Private Room Two',
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

        # Monday, November 23, 2026.
        self.window_start = epoch(2026, 11, 23, 8)
        self.window_end = epoch(2026, 11, 23, 13)
        self.now = epoch(2026, 11, 23, 7)

    def tearDown(self):
        self.tmp.cleanup()

    def _slots(self, **kwargs):
        params = dict(
            organization_slug='solutions',
            site_slug='main',
            calendar_slug='consulting',
            service_slug='consultation',
            window_start_at=self.window_start,
            window_end_at=self.window_end,
            now=self.now,
            step_minutes=15,
        )
        params.update(kwargs)
        return scheduling_public.list_public_slots(**params)

    def test_public_services_expose_only_published_site_calendar_service(self):
        services = scheduling_public.list_public_services(
            'solutions', 'main'
        )
        self.assertEqual(1, len(services))
        service = services[0]
        self.assertEqual('consulting', service.calendar_slug)
        self.assertEqual('consultation', service.service_slug)
        self.assertFalse(hasattr(service, 'calendar_id'))
        self.assertFalse(hasattr(service, 'resource_id'))

        scheduling_calendars.create_service_type(
            'solutions',
            self.calendar.id,
            slug='draft',
            name='Draft',
            duration_minutes=30,
            status='draft',
        )
        self.assertEqual(
            ['consultation'],
            [
                row.service_slug
                for row in scheduling_public.list_public_services(
                    'solutions', 'main'
                )
            ],
        )

    def test_unpublished_site_hides_services_and_slots(self):
        tenant_sites.update_site(
            'solutions', 'main', status='draft'
        )
        self.assertEqual(
            [],
            scheduling_public.list_public_services(
                'solutions', 'main'
            ),
        )
        self.assertEqual([], self._slots())

    def test_slots_hide_resource_identity_and_aggregate_capacity(self):
        slots = self._slots()
        self.assertTrue(slots)
        first = slots[0]
        self.assertEqual(epoch(2026, 11, 23, 9), first.start_at)
        self.assertEqual(epoch(2026, 11, 23, 10), first.end_at)
        self.assertEqual(2, first.available_resource_count)
        self.assertFalse(hasattr(first, 'resource_id'))
        self.assertFalse(hasattr(first, 'resource_name'))
        self.assertFalse(hasattr(first, 'user_id'))

    def test_minimum_notice_removes_earlier_slots(self):
        slots = self._slots(
            now=epoch(2026, 11, 23, 9, 30)
        )
        self.assertTrue(slots)
        self.assertGreaterEqual(
            slots[0].start_at,
            epoch(2026, 11, 23, 10, 30),
        )

    def test_booking_horizon_is_enforced(self):
        scheduling_calendars.update_calendar(
            'solutions',
            self.calendar.id,
            booking_horizon_days=1,
        )
        slots = self._slots(
            window_start_at=epoch(2026, 11, 25, 8),
            window_end_at=epoch(2026, 11, 25, 13),
        )
        self.assertEqual([], slots)

    def test_blackout_reduces_capacity_without_exposing_reason(self):
        scheduling_availability.add_blackout(
            'solutions',
            self.one.id,
            start_at=epoch(2026, 11, 23, 9),
            end_at=epoch(2026, 11, 23, 10),
            reason='Private reason',
        )
        slots = self._slots()
        nine = next(
            row
            for row in slots
            if row.start_at == epoch(2026, 11, 23, 9)
        )
        self.assertEqual(1, nine.available_resource_count)
        self.assertFalse(hasattr(nine, 'reason'))

    def test_existing_appointment_reduces_public_capacity(self):
        scheduling_appointments.create_appointment(
            'solutions',
            service_id=self.service.id,
            resource_id=self.one.id,
            start_at=epoch(2026, 11, 23, 9),
        )
        slots = self._slots()
        nine = next(
            row
            for row in slots
            if row.start_at == epoch(2026, 11, 23, 9)
        )
        self.assertEqual(1, nine.available_resource_count)

    def test_blackout_plus_appointment_can_remove_slot_entirely(self):
        scheduling_appointments.create_appointment(
            'solutions',
            service_id=self.service.id,
            resource_id=self.one.id,
            start_at=epoch(2026, 11, 23, 9),
        )
        scheduling_availability.add_blackout(
            'solutions',
            self.two.id,
            start_at=epoch(2026, 11, 23, 9),
            end_at=epoch(2026, 11, 23, 10),
        )
        starts = {row.start_at for row in self._slots()}
        self.assertNotIn(epoch(2026, 11, 23, 9), starts)

    def test_public_window_is_bounded(self):
        with self.assertRaises(ValueError):
            self._slots(
                window_start_at=epoch(2026, 11, 23),
                window_end_at=epoch(2026, 12, 25),
            )

    def test_foreign_tenant_or_site_context_exposes_nothing(self):
        self.assertEqual(
            [],
            scheduling_public.list_public_services(
                'adventures', 'main'
            ),
        )
        self.assertEqual(
            [],
            scheduling_public.list_public_slots(
                'adventures',
                'main',
                calendar_slug='consulting',
                service_slug='consultation',
                window_start_at=self.window_start,
                window_end_at=self.window_end,
                now=self.now,
            ),
        )


if __name__ == '__main__':
    unittest.main()
