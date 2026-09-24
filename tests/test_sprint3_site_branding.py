from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import site_branding
import tenant_auth
import tenant_branding
import tenant_sites


class Sprint3SiteBrandingThemeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        tenant_auth.DATA_DIR = data_dir
        tenant_auth.DB_PATH = data_dir / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_main_site_inherits_existing_tenant_branding(self):
        ok, _ = tenant_branding.update_branding(
            'solutions',
            site_name='Solutions Legacy Brand',
            tagline='Existing tenant branding',
            primary_color='#112233',
            secondary_color='#445566',
        )
        self.assertTrue(ok)

        branding = site_branding.get_branding('solutions', 'main')

        self.assertEqual('Solutions Legacy Brand', branding.site_name)
        self.assertEqual('Existing tenant branding', branding.tagline)
        self.assertEqual('#112233', branding.primary_color)
        self.assertEqual('classic', branding.theme)

    def test_secondary_site_defaults_to_its_own_site_name(self):
        tenant_sites.create_site(
            'solutions',
            slug='campaign',
            name='Campaign Site',
        )

        branding = site_branding.get_branding('solutions', 'campaign')

        self.assertEqual('Campaign Site', branding.site_name)
        self.assertEqual('', branding.tagline)
        self.assertEqual('classic', branding.theme)

    def test_two_sites_in_same_tenant_have_independent_branding(self):
        tenant_sites.create_site('solutions', slug='one', name='One')
        tenant_sites.create_site('solutions', slug='two', name='Two')

        self.assertTrue(
            site_branding.update_branding(
                'solutions',
                'one',
                site_name='Site One',
                primary_color='#111111',
                secondary_color='#222222',
                theme='minimal',
            )[0]
        )

        self.assertEqual(
            'Site One',
            site_branding.get_branding('solutions', 'one').site_name,
        )
        self.assertEqual(
            'Two',
            site_branding.get_branding('solutions', 'two').site_name,
        )

    def test_same_site_slug_in_different_tenants_is_isolated(self):
        tenant_sites.create_site('solutions', slug='campaign', name='Solutions Campaign')
        tenant_sites.create_site(
            'personal-training',
            slug='campaign',
            name='Training Campaign',
        )

        self.assertTrue(
            site_branding.update_branding(
                'solutions',
                'campaign',
                site_name='Solutions Brand',
                theme='bold',
            )[0]
        )

        self.assertEqual(
            'Solutions Brand',
            site_branding.get_branding('solutions', 'campaign').site_name,
        )
        self.assertEqual(
            'Training Campaign',
            site_branding.get_branding(
                'personal-training', 'campaign'
            ).site_name,
        )

    def test_invalid_theme_is_rejected(self):
        ok, message = site_branding.update_branding(
            'solutions',
            'main',
            site_name='Brand',
            theme='javascript',
        )

        self.assertFalse(ok)
        self.assertIn('Theme', message)

    def test_invalid_color_logo_and_email_are_rejected(self):
        self.assertFalse(
            site_branding.update_branding(
                'solutions',
                'main',
                site_name='Brand',
                primary_color='blue',
            )[0]
        )
        self.assertFalse(
            site_branding.update_branding(
                'solutions',
                'main',
                site_name='Brand',
                logo_url='javascript:alert(1)',
            )[0]
        )
        self.assertFalse(
            site_branding.update_branding(
                'solutions',
                'main',
                site_name='Brand',
                support_email='not-an-email',
            )[0]
        )

    def test_unknown_or_cross_tenant_site_is_rejected(self):
        tenant_sites.create_site('solutions', slug='private', name='Private')

        self.assertIsNone(
            site_branding.get_branding('personal-training', 'private')
        )
        ok, message = site_branding.update_branding(
            'personal-training',
            'private',
            site_name='Wrong Tenant',
        )
        self.assertFalse(ok)
        self.assertEqual('Site not found.', message)

    def test_archived_site_cannot_be_updated(self):
        tenant_sites.create_site('solutions', slug='seasonal', name='Seasonal')
        tenant_sites.archive_site('solutions', 'seasonal')

        ok, message = site_branding.update_branding(
            'solutions',
            'seasonal',
            site_name='Archived Brand',
        )

        self.assertFalse(ok)
        self.assertIn('Archived', message)

    def test_site_branding_override_does_not_modify_legacy_tenant_branding(self):
        before = tenant_branding.get_branding('solutions')

        self.assertTrue(
            site_branding.update_branding(
                'solutions',
                'main',
                site_name='Builder Brand',
                theme='minimal',
            )[0]
        )

        self.assertEqual(
            'Builder Brand',
            site_branding.get_branding('solutions', 'main').site_name,
        )
        self.assertEqual(
            before.site_name,
            tenant_branding.get_branding('solutions').site_name,
        )


if __name__ == '__main__':
    unittest.main()
