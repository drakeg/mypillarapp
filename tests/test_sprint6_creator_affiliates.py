from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import creator_affiliates
import tenant_auth
import tenant_sites


class Sprint6CreatorAffiliateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_affiliate_with_disclosure_metadata(self):
        affiliate = creator_affiliates.create_affiliate(
            'solutions',
            'main',
            label='Camera gear',
            destination_url='https://example.com/gear?tag=mallards',
            disclosure_text='We may earn a commission from qualifying purchases.',
            network='Example Network',
            program='Gear Program',
            tracking_code='tag=mallards',
            position=10,
            status='published',
        )
        self.assertEqual('published', affiliate.status)
        self.assertEqual('Example Network', affiliate.network)
        self.assertIn('commission', affiliate.disclosure_text)

    def test_destination_requires_credential_free_https(self):
        for url in (
            '',
            'http://example.com/product',
            'https://user:secret@example.com/product',
            'javascript:alert(1)',
            'ftp://example.com/file',
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    creator_affiliates.create_affiliate(
                        'solutions',
                        'main',
                        label='Unsafe',
                        destination_url=url,
                        disclosure_text='Affiliate disclosure',
                    )

    def test_disclosure_is_required_and_script_content_is_rejected(self):
        with self.assertRaises(ValueError):
            creator_affiliates.create_affiliate(
                'solutions',
                'main',
                label='Missing disclosure',
                destination_url='https://example.com',
                disclosure_text=' ',
            )
        for value in (
            '<script>alert(1)</script>',
            'javascript:alert(1)',
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    creator_affiliates.create_affiliate(
                        'solutions',
                        'main',
                        label='Unsafe disclosure',
                        destination_url='https://example.com',
                        disclosure_text=value,
                    )

    def test_tracking_code_is_data_not_executable_script(self):
        affiliate = creator_affiliates.create_affiliate(
            'solutions',
            'main',
            label='Tracked',
            destination_url='https://example.com/product',
            disclosure_text='Affiliate link',
            tracking_code='utm_source=madmallards&ref=abc123',
        )
        self.assertEqual(
            'utm_source=madmallards&ref=abc123',
            affiliate.tracking_code,
        )
        with self.assertRaises(ValueError):
            creator_affiliates.create_affiliate(
                'solutions',
                'main',
                label='Bad tracking',
                destination_url='https://example.com/product',
                disclosure_text='Affiliate link',
                tracking_code='<script src="https://evil.example/x.js"></script>',
            )

    def test_published_filter_and_deterministic_order(self):
        third = creator_affiliates.create_affiliate(
            'solutions', 'main',
            label='Third',
            destination_url='https://example.com/3',
            disclosure_text='Affiliate',
            position=20,
            status='published',
        )
        first = creator_affiliates.create_affiliate(
            'solutions', 'main',
            label='First',
            destination_url='https://example.com/1',
            disclosure_text='Affiliate',
            position=10,
            status='published',
        )
        second = creator_affiliates.create_affiliate(
            'solutions', 'main',
            label='Second',
            destination_url='https://example.com/2',
            disclosure_text='Affiliate',
            position=10,
            status='published',
        )
        creator_affiliates.create_affiliate(
            'solutions', 'main',
            label='Draft',
            destination_url='https://example.com/draft',
            disclosure_text='Affiliate',
            status='draft',
        )
        published = creator_affiliates.list_affiliates(
            'solutions', 'main', published_only=True
        )
        self.assertEqual(
            [first.id, second.id, third.id],
            [row.id for row in published],
        )

    def test_cross_site_and_cross_tenant_access_fail_closed(self):
        tenant_sites.create_site(
            'solutions', slug='creator', name='Creator'
        )
        row = creator_affiliates.create_affiliate(
            'solutions',
            'creator',
            label='Private',
            destination_url='https://example.com/private',
            disclosure_text='Affiliate',
        )
        self.assertIsNone(
            creator_affiliates.get_affiliate(
                'solutions', 'main', row.id
            )
        )
        self.assertIsNone(
            creator_affiliates.get_affiliate(
                'personal-training', 'main', row.id
            )
        )
        self.assertIsNone(
            creator_affiliates.update_affiliate(
                'personal-training', 'main', row.id,
                label='Wrong tenant',
            )
        )

    def test_archived_affiliate_is_immutable_and_hidden(self):
        row = creator_affiliates.create_affiliate(
            'solutions',
            'main',
            label='Archive me',
            destination_url='https://example.com/archive',
            disclosure_text='Affiliate',
        )
        archived = creator_affiliates.archive_affiliate(
            'solutions', 'main', row.id
        )
        self.assertEqual('archived', archived.status)
        self.assertEqual(
            [],
            creator_affiliates.list_affiliates(
                'solutions', 'main'
            ),
        )
        with self.assertRaises(ValueError):
            creator_affiliates.update_affiliate(
                'solutions', 'main', row.id,
                label='Nope',
            )

    def test_archived_site_cannot_be_modified(self):
        tenant_sites.create_site(
            'solutions', slug='seasonal', name='Seasonal'
        )
        tenant_sites.archive_site('solutions', 'seasonal')
        with self.assertRaises(ValueError):
            creator_affiliates.create_affiliate(
                'solutions',
                'seasonal',
                label='Nope',
                destination_url='https://example.com/nope',
                disclosure_text='Affiliate',
            )


if __name__ == '__main__':
    unittest.main()
