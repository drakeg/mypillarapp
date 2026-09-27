from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import form_config
import public_site_renderer
import site_forms
import site_media
import site_navigation
import site_pages
import site_services
import solutions_site_migration
import tenant_auth
import tenant_sites


class Sprint3SolutionsCompatibilityMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

    def tearDown(self):
        self.tmp.cleanup()

    def test_seed_creates_staged_content_without_activating_site(self):
        result = solutions_site_migration.migrate_solutions_content()
        self.assertEqual((2, 3, 1, 3, 2), (
            result.created_pages, result.created_services,
            result.created_forms, result.created_navigation,
            result.created_media,
        ))
        self.assertEqual('draft', tenant_sites.get_site('solutions', 'main').status)
        self.assertTrue(all(p.status == 'draft' for p in site_pages.list_pages('solutions', 'main')))
        self.assertTrue(all(s.status == 'draft' for s in site_services.list_services('solutions', 'main')))
        self.assertTrue(all(f.status == 'draft' for f in site_forms.list_forms('solutions', 'main')))
        self.assertTrue(all(m.status == 'draft' for m in site_media.list_media('solutions', 'main')))
        self.assertFalse(any(n.is_visible for n in site_navigation.list_items('solutions', 'main')))

    def test_second_run_is_idempotent_and_does_not_overwrite_edits(self):
        solutions_site_migration.migrate_solutions_content()
        site_pages.update_page('solutions', 'main', 'home', title='Owner edited title')
        result = solutions_site_migration.migrate_solutions_content()
        self.assertEqual((0, 0, 0, 0, 0), (
            result.created_pages, result.created_services,
            result.created_forms, result.created_navigation,
            result.created_media,
        ))
        self.assertEqual('Owner edited title', site_pages.get_page('solutions', 'main', 'home').title)
        self.assertEqual(3, len(site_navigation.list_items('solutions', 'main')))

    def test_existing_records_are_not_replaced(self):
        site_services.create_service('solutions', 'main', slug='aws-cloud-setup',
                                     name='Custom AWS', status='published')
        result = solutions_site_migration.migrate_solutions_content()
        self.assertEqual(2, result.created_services)
        self.assertEqual('Custom AWS', site_services.get_service('solutions', 'main', 'aws-cloud-setup').name)

    def test_form_snapshot_does_not_change_live_validation(self):
        expected = form_config.public_form_config()
        solutions_site_migration.migrate_solutions_content()
        form = site_forms.get_form('solutions', 'main', 'project-request')
        self.assertEqual([f['name'] for f in expected['fields']],
                         [f['name'] for f in form.fields])
        self.assertEqual(expected, form_config.public_form_config())
        self.assertEqual([], site_forms.list_forms('solutions', 'main', published_only=True))

    def test_cross_tenant_content_remains_untouched(self):
        solutions_site_migration.migrate_solutions_content()
        self.assertEqual([], site_pages.list_pages('adventures', 'main'))
        self.assertEqual([], site_services.list_services('personal-training', 'main'))
        self.assertEqual([], site_media.list_media('adventures', 'main'))

    def test_static_solutions_renderer_fallback_is_preserved(self):
        solutions_site_migration.migrate_solutions_content()
        self.assertIsNone(
            public_site_renderer.render_public_path(tenant_auth.PRIMARY_DOMAIN, '/')
        )

    def test_archived_solutions_site_cannot_be_migrated(self):
        tenant_sites.archive_site('solutions', 'main')
        with self.assertRaisesRegex(ValueError, 'active Solutions main'):
            solutions_site_migration.migrate_solutions_content()

    def test_does_not_change_other_published_sites(self):
        tenant_sites.create_site(
            'adventures', slug='travel', name='Travel', status='published'
        )
        solutions_site_migration.migrate_solutions_content()
        self.assertEqual('published', tenant_sites.get_site('adventures', 'travel').status)


if __name__ == '__main__':
    unittest.main()
