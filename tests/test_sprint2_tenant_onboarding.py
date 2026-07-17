from pathlib import Path
import importlib
import sys
import tempfile
import unittest
from unittest.mock import patch

SITE_DIR = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SITE_DIR) not in sys.path:
    sys.path.insert(0, str(SITE_DIR))

import messaging
import tenant_auth
import tenant_branding
import tenant_context
import tenant_onboarding
import tenant_organizations


class Sprint2TenantOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        messaging.DATA_DIR = data
        messaging.DB_PATH = data / 'madmallard.sqlite3'
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        importlib.reload(tenant_context)
        importlib.reload(tenant_branding)
        importlib.reload(tenant_organizations)
        importlib.reload(tenant_onboarding)

    def tearDown(self):
        self.tmp.cleanup()

    def onboard(self, **overrides):
        values = {
            'slug': 'new-client',
            'organization_name': 'New Client LLC',
            'primary_domain': 'client.example.com',
            'owner_first_name': 'Taylor',
            'owner_last_name': 'Owner',
            'owner_email': 'owner@example.com',
            'owner_password': 'VerySecurePass123!',
            'site_name': 'New Client',
            'tagline': 'Ready to launch.',
            'primary_color': '#112233',
            'secondary_color': '#445566',
            'support_email': 'support@example.com',
        }
        values.update(overrides)
        sent = []
        with patch.object(
            messaging,
            'send_email',
            side_effect=lambda *args: sent.append(args) or True,
        ):
            result = tenant_onboarding.onboard_tenant(**values)
        return result, sent

    def test_onboarding_creates_active_tenant_and_primary_domain(self):
        (ok, _, result), _ = self.onboard()
        self.assertTrue(ok)
        self.assertEqual(result.organization_slug, 'new-client')
        tenant = tenant_context.resolve_tenant('client.example.com')
        self.assertEqual(tenant.slug, 'new-client')
        self.assertEqual(tenant.status, 'active')

    def test_onboarding_creates_inactive_owner_account(self):
        (ok, _, _), _ = self.onboard()
        self.assertTrue(ok)
        with tenant_auth.db() as conn:
            row = conn.execute(
                '''SELECT u.email, u.role, u.is_active, o.slug
                   FROM auth_users u
                   JOIN auth_organizations o ON o.id = u.organization_id
                   WHERE o.slug = 'new-client' ''',
            ).fetchone()
        self.assertEqual(row['email'], 'owner@example.com')
        self.assertEqual(row['role'], 'owner')
        self.assertEqual(row['is_active'], 0)

    def test_onboarding_persists_branding(self):
        self.onboard()
        branding = tenant_branding.get_branding('new-client')
        self.assertEqual(branding.site_name, 'New Client')
        self.assertEqual(branding.tagline, 'Ready to launch.')
        self.assertEqual(branding.primary_color, '#112233')
        self.assertEqual(branding.secondary_color, '#445566')
        self.assertEqual(branding.support_email, 'support@example.com')

    def test_onboarding_sends_owner_verification_to_tenant_domain(self):
        (_, _, _), sent = self.onboard()
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][3], 'owner@example.com')
        self.assertIn(
            'https://client.example.com/verify-email/',
            sent[0][1],
        )

    def test_invalid_branding_does_not_create_tenant(self):
        (ok, message, result), sent = self.onboard(primary_color='blue')
        self.assertFalse(ok)
        self.assertIn('Primary color', message)
        self.assertIsNone(result)
        self.assertEqual(sent, [])
        self.assertIsNone(tenant_organizations.get_organization('new-client'))

    def test_conflicting_domain_does_not_create_second_tenant(self):
        self.onboard()
        (ok, message, result), sent = self.onboard(
            slug='second-client',
            organization_name='Second Client',
            owner_email='second@example.com',
        )
        self.assertFalse(ok)
        self.assertIn('domain', message.lower())
        self.assertIsNone(result)
        self.assertEqual(sent, [])
        self.assertIsNone(tenant_organizations.get_organization('second-client'))


if __name__ == '__main__':
    unittest.main()
