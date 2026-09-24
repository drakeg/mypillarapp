from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import site_pages
import tenant_auth
import tenant_sites


class Sprint3PageContentModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        tenant_auth.DATA_DIR = data_dir
        tenant_auth.DB_PATH = data_dir / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_and_get_page(self):
        page = site_pages.create_page(
            'solutions',
            'main',
            slug='about-us',
            title='About Us',
            summary='Who we are',
            body='Plain text body',
            status='published',
            position=10,
        )

        fetched = site_pages.get_page('solutions', 'main', 'about-us')

        self.assertEqual(page.id, fetched.id)
        self.assertEqual('About Us', fetched.title)
        self.assertEqual('Plain text body', fetched.body)

    def test_same_slug_allowed_on_different_sites(self):
        tenant_sites.create_site('solutions', slug='campaign', name='Campaign')
        site_pages.create_page(
            'solutions', 'main', slug='about', title='Main About'
        )
        site_pages.create_page(
            'solutions', 'campaign', slug='about', title='Campaign About'
        )

        self.assertEqual(
            'Main About',
            site_pages.get_page('solutions', 'main', 'about').title,
        )
        self.assertEqual(
            'Campaign About',
            site_pages.get_page('solutions', 'campaign', 'about').title,
        )

    def test_duplicate_slug_rejected_within_site(self):
        site_pages.create_page(
            'solutions', 'main', slug='about', title='About'
        )
        with self.assertRaisesRegex(ValueError, 'already exists'):
            site_pages.create_page(
                'solutions', 'main', slug='about', title='Duplicate'
            )

    def test_cross_tenant_lookup_and_update_fail(self):
        site_pages.create_page(
            'solutions', 'main', slug='private', title='Private'
        )

        self.assertIsNone(
            site_pages.get_page('personal-training', 'main', 'private')
        )
        self.assertIsNone(
            site_pages.update_page(
                'personal-training',
                'main',
                'private',
                title='Wrong Tenant',
            )
        )
        self.assertEqual(
            'Private',
            site_pages.get_page('solutions', 'main', 'private').title,
        )

    def test_list_pages_is_ordered_and_scoped(self):
        site_pages.create_page(
            'solutions', 'main', slug='second', title='Second', position=20
        )
        site_pages.create_page(
            'solutions', 'main', slug='first', title='First', position=10
        )
        site_pages.create_page(
            'personal-training',
            'main',
            slug='training',
            title='Training',
            position=0,
        )

        pages = site_pages.list_pages('solutions', 'main')

        self.assertEqual(['first', 'second'], [page.slug for page in pages])

    def test_published_only_filter(self):
        site_pages.create_page(
            'solutions',
            'main',
            slug='draft',
            title='Draft',
            status='draft',
        )
        site_pages.create_page(
            'solutions',
            'main',
            slug='live',
            title='Live',
            status='published',
        )

        pages = site_pages.list_pages(
            'solutions', 'main', published_only=True
        )

        self.assertEqual(['live'], [page.slug for page in pages])

    def test_archive_preserves_record_but_hides_default_listing(self):
        site_pages.create_page(
            'solutions',
            'main',
            slug='old',
            title='Old',
            status='published',
        )

        archived = site_pages.archive_page('solutions', 'main', 'old')

        self.assertEqual('archived', archived.status)
        self.assertNotIn(
            'old',
            [page.slug for page in site_pages.list_pages('solutions', 'main')],
        )
        self.assertIn(
            'old',
            [
                page.slug
                for page in site_pages.list_pages(
                    'solutions', 'main', include_archived=True
                )
            ],
        )

    def test_archived_page_cannot_be_modified(self):
        site_pages.create_page(
            'solutions', 'main', slug='old', title='Old'
        )
        site_pages.archive_page('solutions', 'main', 'old')

        with self.assertRaises(ValueError):
            site_pages.update_page(
                'solutions', 'main', 'old', title='Updated'
            )

    def test_archived_site_cannot_receive_or_update_pages(self):
        tenant_sites.create_site('solutions', slug='seasonal', name='Seasonal')
        site_pages.create_page(
            'solutions', 'seasonal', slug='page', title='Page'
        )
        tenant_sites.archive_site('solutions', 'seasonal')

        with self.assertRaises(ValueError):
            site_pages.create_page(
                'solutions', 'seasonal', slug='new', title='New'
            )
        with self.assertRaises(ValueError):
            site_pages.update_page(
                'solutions', 'seasonal', 'page', title='Nope'
            )

    def test_invalid_slug_title_status_and_position_are_rejected(self):
        cases = [
            dict(slug='../bad', title='Bad'),
            dict(slug='good', title=' '),
            dict(slug='good', title='Good', status='active'),
            dict(slug='good', title='Good', position=-1),
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    site_pages.create_page('solutions', 'main', **kwargs)

    def test_body_is_stored_as_content_not_executed_or_rendered(self):
        body = '<script>alert("x")</script> Plain text content'
        site_pages.create_page(
            'solutions',
            'main',
            slug='content',
            title='Content',
            body=body,
        )

        fetched = site_pages.get_page('solutions', 'main', 'content')

        self.assertEqual(body, fetched.body)


if __name__ == '__main__':
    unittest.main()
