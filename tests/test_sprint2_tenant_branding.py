from pathlib import Path
import importlib
import sys
import tempfile
import unittest

SITE_DIR = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SITE_DIR) not in sys.path:
    sys.path.insert(0, str(SITE_DIR))

import messaging
import tenant_auth
import tenant_context
import tenant_branding


class Sprint2TenantBrandingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)

        messaging.DATA_DIR = data
        messaging.DB_PATH = data / 'madmallard.sqlite3'
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'

        importlib.reload(tenant_context)
        importlib.reload(tenant_branding)

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_use_tenant_name(self):
        branding = tenant_branding.get_branding('solutions')
        self.assertEqual(branding.site_name, 'Mad Mallard Solutions')
        self.assertEqual(branding.primary_color, '#1f6f5f')

    def test_branding_is_tenant_scoped(self):
        ok, _ = tenant_branding.update_branding(
            'solutions',
            site_name='Solutions Brand',
            primary_color='#112233',
            secondary_color='#445566',
        )
        self.assertTrue(ok)
        self.assertEqual(
            tenant_branding.get_branding('solutions').site_name,
            'Solutions Brand',
        )
        self.assertEqual(
            tenant_branding.get_branding('adventures').site_name,
            'Mad Mallards Adventures',
        )

    def test_unknown_tenant_is_rejected(self):
        self.assertIsNone(tenant_branding.get_branding('missing'))
        ok, message = tenant_branding.update_branding(
            'missing',
            site_name='Missing',
        )
        self.assertFalse(ok)
        self.assertEqual(message, 'Tenant not found.')

    def test_invalid_colors_are_rejected(self):
        ok, message = tenant_branding.update_branding(
            'solutions',
            site_name='Brand',
            primary_color='blue',
        )
        self.assertFalse(ok)
        self.assertIn('Primary color', message)

    def test_invalid_logo_url_is_rejected(self):
        ok, message = tenant_branding.update_branding(
            'solutions',
            site_name='Brand',
            logo_url='javascript:alert(1)',
        )
        self.assertFalse(ok)
        self.assertIn('Logo URL', message)

    def test_complete_branding_round_trip(self):
        ok, _ = tenant_branding.update_branding(
            'personal-training',
            site_name='Mallard Fitness',
            tagline='Train anywhere.',
            logo_url='https://example.com/logo.png',
            primary_color='#123456',
            secondary_color='#abcdef',
            support_email='Coach@Example.com',
        )
        self.assertTrue(ok)

        branding = tenant_branding.get_branding('personal-training')
        self.assertEqual(branding.site_name, 'Mallard Fitness')
        self.assertEqual(branding.tagline, 'Train anywhere.')
        self.assertEqual(branding.logo_url, 'https://example.com/logo.png')
        self.assertEqual(branding.primary_color, '#123456')
        self.assertEqual(branding.secondary_color, '#abcdef')
        self.assertEqual(branding.support_email, 'coach@example.com')


if __name__ == '__main__':
    unittest.main()
