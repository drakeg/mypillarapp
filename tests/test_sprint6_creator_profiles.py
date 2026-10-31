from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import creator_profiles
import tenant_auth
import tenant_sites


class Sprint6CreatorProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

    def tearDown(self):
        self.tmp.cleanup()

    def test_profile_is_unique_and_site_scoped(self):
        first = creator_profiles.upsert_profile(
            'solutions',
            'main',
            display_name='Mad Mallard Creator',
            bio='Outdoor creator',
            avatar_url='https://example.com/avatar.jpg',
            status='published',
        )
        second = creator_profiles.upsert_profile(
            'solutions',
            'main',
            display_name='Updated Creator',
            bio='Updated',
            status='draft',
        )
        self.assertEqual(first.site_id, second.site_id)
        self.assertEqual('Updated Creator', second.display_name)
        self.assertEqual('draft', second.status)
        self.assertIsNone(
            creator_profiles.get_profile(
                'personal-training', 'main'
            )
        )

    def test_profile_validation_and_archive(self):
        with self.assertRaises(ValueError):
            creator_profiles.upsert_profile(
                'solutions', 'main', display_name=' '
            )
        for url in (
            'http://example.com/avatar.jpg',
            'https://user:pass@example.com/avatar.jpg',
            'javascript:alert(1)',
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    creator_profiles.upsert_profile(
                        'solutions',
                        'main',
                        display_name='Creator',
                        avatar_url=url,
                    )

        creator_profiles.upsert_profile(
            'solutions', 'main', display_name='Creator'
        )
        archived = creator_profiles.archive_profile(
            'solutions', 'main'
        )
        self.assertEqual('archived', archived.status)
        with self.assertRaises(ValueError):
            creator_profiles.upsert_profile(
                'solutions', 'main',
                display_name='Resurrected',
            )

    def test_links_support_safe_internal_and_https_targets(self):
        internal = creator_profiles.create_link(
            'solutions', 'main',
            label='About',
            target='/about',
            status='published',
        )
        external = creator_profiles.create_link(
            'solutions', 'main',
            label='YouTube',
            target='https://example.com/channel',
            status='published',
        )
        self.assertEqual('/about', internal.target)
        self.assertEqual(
            'https://example.com/channel', external.target
        )

    def test_unsafe_link_targets_are_rejected(self):
        for target in (
            '',
            '//evil.example.com',
            'http://example.com',
            'https://user:secret@example.com/path',
            'javascript:alert(1)',
            'ftp://example.com/file',
        ):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    creator_profiles.create_link(
                        'solutions', 'main',
                        label='Unsafe',
                        target=target,
                    )

    def test_links_are_deterministically_ordered_and_filtered(self):
        third = creator_profiles.create_link(
            'solutions', 'main',
            label='Third', target='/third', position=20,
            status='published',
        )
        first = creator_profiles.create_link(
            'solutions', 'main',
            label='First', target='/first', position=10,
            status='published',
        )
        second = creator_profiles.create_link(
            'solutions', 'main',
            label='Second', target='/second', position=10,
            status='published',
        )
        creator_profiles.create_link(
            'solutions', 'main',
            label='Draft', target='/draft', position=0,
            status='draft',
        )

        published = creator_profiles.list_links(
            'solutions', 'main', published_only=True
        )
        self.assertEqual(
            [first.id, second.id, third.id],
            [link.id for link in published],
        )

    def test_cross_site_and_cross_tenant_access_fail_closed(self):
        tenant_sites.create_site(
            'solutions', slug='creator', name='Creator'
        )
        link = creator_profiles.create_link(
            'solutions', 'creator',
            label='Private', target='/private'
        )

        self.assertIsNone(
            creator_profiles.get_link(
                'solutions', 'main', link.id
            )
        )
        self.assertIsNone(
            creator_profiles.get_link(
                'personal-training', 'main', link.id
            )
        )
        self.assertIsNone(
            creator_profiles.update_link(
                'personal-training', 'main', link.id,
                label='Wrong tenant',
            )
        )

    def test_archived_links_are_immutable_and_hidden_by_default(self):
        link = creator_profiles.create_link(
            'solutions', 'main',
            label='Archive me', target='/archive'
        )
        archived = creator_profiles.archive_link(
            'solutions', 'main', link.id
        )
        self.assertEqual('archived', archived.status)
        self.assertEqual(
            [],
            creator_profiles.list_links('solutions', 'main'),
        )
        with self.assertRaises(ValueError):
            creator_profiles.update_link(
                'solutions', 'main', link.id,
                label='Nope',
            )

    def test_archived_site_cannot_be_modified(self):
        tenant_sites.create_site(
            'solutions', slug='seasonal', name='Seasonal'
        )
        tenant_sites.archive_site('solutions', 'seasonal')
        with self.assertRaises(ValueError):
            creator_profiles.upsert_profile(
                'solutions', 'seasonal',
                display_name='Nope',
            )
        with self.assertRaises(ValueError):
            creator_profiles.create_link(
                'solutions', 'seasonal',
                label='Nope', target='/nope',
            )


if __name__ == '__main__':
    unittest.main()
