from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import scheduling_calendars
import tenant_auth
import tenant_sites


class Sprint9CalendarServiceTypeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()
        scheduling_calendars.ensure_schema()

    def tearDown(self):
        self.tmp.cleanup()

    def test_calendar_is_tenant_scoped_and_site_link_is_same_tenant(self):
        own_site = tenant_sites.get_site('solutions', 'main')
        other_site = tenant_sites.get_site('adventures', 'main')

        calendar = scheduling_calendars.create_calendar(
            'solutions',
            slug='consulting',
            name='Consulting',
            timezone_name='America/New_York',
            site_id=own_site.id,
        )
        self.assertEqual('solutions', calendar.organization_slug)
        self.assertEqual(own_site.id, calendar.site_id)
        self.assertIsNone(
            scheduling_calendars.get_calendar(
                'adventures', calendar.id
            )
        )

        with self.assertRaises(PermissionError):
            scheduling_calendars.create_calendar(
                'solutions',
                slug='wrong-site',
                name='Wrong Site',
                timezone_name='America/New_York',
                site_id=other_site.id,
            )

    def test_calendar_validates_timezone_horizon_and_notice(self):
        with self.assertRaises(ValueError):
            scheduling_calendars.create_calendar(
                'solutions',
                slug='bad-zone',
                name='Bad Zone',
                timezone_name='Not/AZone',
            )
        with self.assertRaises(ValueError):
            scheduling_calendars.create_calendar(
                'solutions',
                slug='bad-horizon',
                name='Bad Horizon',
                timezone_name='UTC',
                booking_horizon_days=0,
            )
        with self.assertRaises(ValueError):
            scheduling_calendars.create_calendar(
                'solutions',
                slug='bad-notice',
                name='Bad Notice',
                timezone_name='UTC',
                minimum_notice_minutes=-1,
            )

    def test_calendar_slug_is_unique_per_tenant(self):
        scheduling_calendars.create_calendar(
            'solutions',
            slug='consulting',
            name='Consulting',
            timezone_name='UTC',
        )
        with self.assertRaises(ValueError):
            scheduling_calendars.create_calendar(
                'solutions',
                slug='consulting',
                name='Another',
                timezone_name='UTC',
            )
        other = scheduling_calendars.create_calendar(
            'adventures',
            slug='consulting',
            name='Adventure Consulting',
            timezone_name='UTC',
        )
        self.assertEqual('adventures', other.organization_slug)

    def test_published_calendar_filter_and_archive_immutability(self):
        draft = scheduling_calendars.create_calendar(
            'solutions',
            slug='draft',
            name='Draft',
            timezone_name='UTC',
        )
        live = scheduling_calendars.create_calendar(
            'solutions',
            slug='live',
            name='Live',
            timezone_name='UTC',
            status='published',
        )
        published = scheduling_calendars.list_calendars(
            'solutions', published_only=True
        )
        self.assertEqual([live.id], [row.id for row in published])

        archived = scheduling_calendars.archive_calendar(
            'solutions', draft.id
        )
        self.assertEqual('archived', archived.status)
        with self.assertRaises(ValueError):
            scheduling_calendars.update_calendar(
                'solutions', draft.id, name='Nope'
            )

    def test_service_type_is_scoped_to_tenant_calendar(self):
        calendar = scheduling_calendars.create_calendar(
            'solutions',
            slug='consulting',
            name='Consulting',
            timezone_name='UTC',
        )
        service = scheduling_calendars.create_service_type(
            'solutions',
            calendar.id,
            slug='discovery-call',
            name='Discovery Call',
            duration_minutes=30,
            buffer_before_minutes=5,
            buffer_after_minutes=10,
        )
        self.assertEqual(calendar.id, service.calendar_id)
        self.assertEqual(30, service.duration_minutes)
        self.assertIsNone(
            scheduling_calendars.get_service_type(
                'adventures', service.id
            )
        )
        with self.assertRaises(PermissionError):
            scheduling_calendars.create_service_type(
                'adventures',
                calendar.id,
                slug='foreign',
                name='Foreign',
                duration_minutes=30,
            )

    def test_service_duration_and_buffers_are_bounded(self):
        calendar = scheduling_calendars.create_calendar(
            'solutions',
            slug='consulting',
            name='Consulting',
            timezone_name='UTC',
        )
        for duration in (0, 1441):
            with self.assertRaises(ValueError):
                scheduling_calendars.create_service_type(
                    'solutions',
                    calendar.id,
                    slug=f'bad-{duration}',
                    name='Bad',
                    duration_minutes=duration,
                )
        with self.assertRaises(ValueError):
            scheduling_calendars.create_service_type(
                'solutions',
                calendar.id,
                slug='bad-buffer',
                name='Bad Buffer',
                duration_minutes=30,
                buffer_before_minutes=1441,
            )

    def test_service_slug_is_unique_per_calendar_not_globally(self):
        first = scheduling_calendars.create_calendar(
            'solutions',
            slug='one',
            name='One',
            timezone_name='UTC',
        )
        second = scheduling_calendars.create_calendar(
            'solutions',
            slug='two',
            name='Two',
            timezone_name='UTC',
        )
        scheduling_calendars.create_service_type(
            'solutions',
            first.id,
            slug='consultation',
            name='Consultation',
            duration_minutes=60,
        )
        with self.assertRaises(ValueError):
            scheduling_calendars.create_service_type(
                'solutions',
                first.id,
                slug='consultation',
                name='Duplicate',
                duration_minutes=60,
            )
        other = scheduling_calendars.create_service_type(
            'solutions',
            second.id,
            slug='consultation',
            name='Consultation',
            duration_minutes=60,
        )
        self.assertEqual(second.id, other.calendar_id)

    def test_service_publish_filter_archive_and_parent_archive(self):
        calendar = scheduling_calendars.create_calendar(
            'solutions',
            slug='consulting',
            name='Consulting',
            timezone_name='UTC',
        )
        draft = scheduling_calendars.create_service_type(
            'solutions',
            calendar.id,
            slug='draft',
            name='Draft',
            duration_minutes=30,
        )
        live = scheduling_calendars.create_service_type(
            'solutions',
            calendar.id,
            slug='live',
            name='Live',
            duration_minutes=60,
            status='published',
        )
        published = scheduling_calendars.list_service_types(
            'solutions', calendar.id, published_only=True
        )
        self.assertEqual([live.id], [row.id for row in published])

        archived = scheduling_calendars.archive_service_type(
            'solutions', draft.id
        )
        self.assertEqual('archived', archived.status)
        with self.assertRaises(ValueError):
            scheduling_calendars.update_service_type(
                'solutions', draft.id, name='Nope'
            )

        scheduling_calendars.archive_calendar(
            'solutions', calendar.id
        )
        with self.assertRaises(PermissionError):
            scheduling_calendars.create_service_type(
                'solutions',
                calendar.id,
                slug='late',
                name='Late',
                duration_minutes=30,
            )


if __name__ == '__main__':
    unittest.main()
