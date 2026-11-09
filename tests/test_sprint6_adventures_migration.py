from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import adventures_creator_migration
import creator_collections
import creator_profiles
import site_media
import site_navigation
import site_pages
import tenant_auth
import tenant_branding
import tenant_sites


class Sprint6AdventuresCompatibilityMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

    def tearDown(self):
        self.tmp.cleanup()

    def test_safe_legacy_content_is_staged_as_draft(self):
        tenant_branding.update_branding(
            'adventures',
            site_name='Mad Mallards Adventures',
            tagline='RV travel and creator stories',
        )
        site_navigation.create_item(
            'adventures', 'main',
            label='YouTube',
            target='https://example.com/channel',
            position=2,
        )
        site_pages.create_page(
            'adventures', 'main',
            slug='gear',
            title='Gear',
            status='published',
            position=1,
        )
        site_media.create_media(
            'adventures', 'main',
            slug='trip-video',
            kind='video',
            source='https://example.com/video',
            alt_text='Trip video',
            status='published',
        )

        result = adventures_creator_migration.migrate_adventures_content()

        self.assertEqual(1, result.created_profile)
        self.assertEqual(1, result.created_links)
        self.assertEqual(2, result.created_collections)
        self.assertEqual(2, result.created_items)
        self.assertEqual(0, result.unsafe_records)

        profile = creator_profiles.get_profile('adventures', 'main')
        self.assertEqual('Mad Mallards Adventures', profile.display_name)
        self.assertEqual('RV travel and creator stories', profile.bio)
        self.assertEqual('draft', profile.status)

        links = creator_profiles.list_links('adventures', 'main')
        self.assertEqual([('YouTube', 'https://example.com/channel', 'draft')],
                         [(x.label, x.target, x.status) for x in links])
        self.assertTrue(all(
            c.status == 'draft'
            for c in creator_collections.list_collections('adventures', 'main')
        ))

    def test_rerun_is_idempotent_and_preserves_owner_edits(self):
        site_navigation.create_item(
            'adventures', 'main',
            label='Home',
            target='/',
        )
        first = adventures_creator_migration.migrate_adventures_content()
        self.assertEqual(1, first.created_links)
        link = creator_profiles.list_links('adventures', 'main')[0]
        creator_profiles.update_link(
            'adventures', 'main', link.id,
            label='Owner edited',
            target='/creator',
        )
        creator_profiles.upsert_profile(
            'adventures', 'main',
            display_name='Owner edited profile',
            status='draft',
        )

        second = adventures_creator_migration.migrate_adventures_content()

        self.assertEqual(0, second.created_profile)
        self.assertEqual(0, second.created_links)
        self.assertGreaterEqual(second.already_mapped, 2)
        self.assertEqual(
            'Owner edited',
            creator_profiles.list_links('adventures', 'main')[0].label,
        )
        self.assertEqual(
            'Owner edited profile',
            creator_profiles.get_profile('adventures', 'main').display_name,
        )

    def test_unsafe_and_affiliate_like_records_are_reported_not_guessed(self):
        site_navigation.create_item(
            'adventures', 'main',
            label='Affiliate gear',
            target='http://example.com/gear',
        )
        site_media.create_media(
            'adventures', 'main',
            slug='unsafe',
            kind='video',
            source='http://user:pass@example.com/video',
        )

        result = adventures_creator_migration.migrate_adventures_content()

        self.assertEqual(2, result.unsafe_records)
        self.assertEqual(1, result.unmatched_records)
        self.assertEqual([], creator_profiles.list_links('adventures', 'main'))
        self.assertTrue(any('manual disclosure' in issue for issue in result.issues))

    def test_existing_canonical_profile_is_preserved(self):
        creator_profiles.upsert_profile(
            'adventures', 'main',
            display_name='Existing creator',
            bio='Owner-authored',
            status='published',
        )

        result = adventures_creator_migration.migrate_adventures_content()

        self.assertEqual(0, result.created_profile)
        self.assertEqual(1, result.preserved_canonical)
        profile = creator_profiles.get_profile('adventures', 'main')
        self.assertEqual('Existing creator', profile.display_name)
        self.assertEqual('Owner-authored', profile.bio)
        self.assertEqual('published', profile.status)

    def test_migration_does_not_publish_or_cut_over_existing_site(self):
        site = tenant_sites.get_site('adventures', 'main')
        original_status = site.status
        site_navigation.create_item(
            'adventures', 'main',
            label='Creator',
            target='/creator',
            is_visible=True,
        )

        adventures_creator_migration.migrate_adventures_content()

        self.assertEqual(
            original_status,
            tenant_sites.get_site('adventures', 'main').status,
        )
        self.assertTrue(site_navigation.list_items('adventures', 'main')[0].is_visible)
        self.assertEqual(
            [],
            creator_profiles.list_links(
                'adventures', 'main', published_only=True
            ),
        )
        self.assertIsNone(
            creator_profiles.get_profile(
                'adventures', 'main', published_only=True
            )
        )

    def test_other_tenants_are_untouched_and_archived_adventures_fails_closed(self):
        site_navigation.create_item(
            'solutions', 'main',
            label='Solutions',
            target='https://example.com/solutions',
        )
        adventures_creator_migration.migrate_adventures_content()
        self.assertEqual([], creator_profiles.list_links('solutions', 'main'))

        tenant_sites.archive_site('adventures', 'main')
        with self.assertRaisesRegex(ValueError, 'active Adventures main'):
            adventures_creator_migration.migrate_adventures_content()


if __name__ == '__main__':
    unittest.main()
