from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import tenant_auth
import tenant_sites


class Sprint3TenantSiteFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        tenant_auth.DATA_DIR = data_dir
        tenant_auth.DB_PATH = data_dir / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_initial_organizations_receive_separate_main_sites(self):
        solutions = tenant_sites.get_site('solutions', 'main')
        training = tenant_sites.get_site('personal-training', 'main')
        adventures = tenant_sites.get_site('adventures', 'main')

        self.assertIsNotNone(solutions)
        self.assertIsNotNone(training)
        self.assertIsNotNone(adventures)
        self.assertNotEqual(solutions.organization_id, training.organization_id)
        self.assertNotEqual(solutions.organization_id, adventures.organization_id)

    def test_same_site_slug_is_allowed_in_different_organizations(self):
        solutions = tenant_sites.create_site(
            'solutions', slug='campaign', name='Solutions Campaign'
        )
        training = tenant_sites.create_site(
            'personal-training', slug='campaign', name='Training Campaign'
        )

        self.assertEqual('solutions', solutions.organization_slug)
        self.assertEqual('personal-training', training.organization_slug)

    def test_duplicate_slug_is_rejected_within_same_organization(self):
        tenant_sites.create_site('solutions', slug='campaign', name='Campaign')

        with self.assertRaisesRegex(ValueError, 'already exists'):
            tenant_sites.create_site(
                'solutions',
                slug='campaign',
                name='Duplicate Campaign',
            )

    def test_cross_tenant_lookup_does_not_return_site(self):
        tenant_sites.create_site('solutions', slug='private-site', name='Private Site')

        self.assertIsNone(
            tenant_sites.get_site('personal-training', 'private-site')
        )

    def test_list_sites_is_scoped_to_organization(self):
        tenant_sites.create_site('solutions', slug='solutions-extra', name='Extra')
        tenant_sites.create_site(
            'personal-training',
            slug='training-extra',
            name='Training Extra',
        )

        solution_slugs = {site.slug for site in tenant_sites.list_sites('solutions')}
        training_slugs = {
            site.slug for site in tenant_sites.list_sites('personal-training')
        }

        self.assertIn('solutions-extra', solution_slugs)
        self.assertNotIn('training-extra', solution_slugs)
        self.assertIn('training-extra', training_slugs)
        self.assertNotIn('solutions-extra', training_slugs)

    def test_archive_hides_site_from_default_listing_but_preserves_record(self):
        tenant_sites.create_site('solutions', slug='seasonal', name='Seasonal')

        archived = tenant_sites.archive_site('solutions', 'seasonal')

        self.assertEqual('archived', archived.status)
        self.assertNotIn(
            'seasonal',
            {site.slug for site in tenant_sites.list_sites('solutions')},
        )
        self.assertIn(
            'seasonal',
            {
                site.slug
                for site in tenant_sites.list_sites(
                    'solutions', include_archived=True
                )
            },
        )

    def test_update_is_tenant_scoped(self):
        tenant_sites.create_site('solutions', slug='campaign', name='Original')

        self.assertIsNone(
            tenant_sites.update_site(
                'personal-training',
                'campaign',
                name='Wrong Tenant',
            )
        )
        self.assertEqual(
            'Original',
            tenant_sites.get_site('solutions', 'campaign').name,
        )

    def test_invalid_slug_and_status_are_rejected(self):
        with self.assertRaises(ValueError):
            tenant_sites.create_site(
                'solutions',
                slug='../unsafe',
                name='Unsafe',
            )
        with self.assertRaises(ValueError):
            tenant_sites.create_site(
                'solutions',
                slug='valid',
                name='Valid',
                status='active',
            )


if __name__ == '__main__':
    unittest.main()
