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
import tenant_admin_dashboard
import tenant_auth
import tenant_branding
import tenant_context
import tenant_lifecycle
import tenant_onboarding
import tenant_organizations


class Sprint2EndToEndHardeningTests(unittest.TestCase):
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
        importlib.reload(tenant_lifecycle)
        importlib.reload(tenant_admin_dashboard)

    def tearDown(self):
        self.tmp.cleanup()

    def onboard(self, *, slug='hardening', domain='hardening.example.com'):
        with patch.object(messaging, 'send_email', return_value=True):
            return tenant_onboarding.onboard_tenant(
                slug=slug,
                organization_name='Hardening Tenant',
                primary_domain=domain,
                owner_first_name='Test',
                owner_last_name='Owner',
                owner_email=f'owner@{domain}',
                owner_password='HardeningPass123!',
                site_name='Hardening Brand',
                tagline='End-to-end validation',
                primary_color='#123456',
                secondary_color='#abcdef',
                support_email=f'support@{domain}',
            )

    def test_onboarding_connects_domain_branding_and_owner(self):
        ok, message, result = self.onboard()
        self.assertTrue(ok, message)
        self.assertEqual(result.organization_slug, 'hardening')
        self.assertEqual(tenant_context.resolve_tenant('hardening.example.com').slug, 'hardening')
        self.assertEqual(tenant_branding.get_branding('hardening').site_name, 'Hardening Brand')
        summary = next(item for item in tenant_admin_dashboard.list_tenant_summaries() if item.slug == 'hardening')
        self.assertEqual(summary.user_count, 1)

    def test_duplicate_slug_does_not_create_partial_tenant(self):
        self.assertTrue(self.onboard()[0])
        ok, _, result = self.onboard(domain='other.example.com')
        self.assertFalse(ok)
        self.assertIsNone(result)
        organizations = [item for item in tenant_organizations.list_organizations(include_inactive=True) if item['slug'] == 'hardening']
        self.assertEqual(len(organizations), 1)
        self.assertIsNone(tenant_context.resolve_tenant('other.example.com'))

    def test_duplicate_domain_does_not_create_partial_tenant(self):
        self.assertTrue(self.onboard()[0])
        ok, _, result = self.onboard(slug='hardening-two')
        self.assertFalse(ok)
        self.assertIsNone(result)
        self.assertIsNone(tenant_organizations.get_organization('hardening-two'))

    def test_suspend_is_reflected_in_resolution_and_admin_dashboard(self):
        self.assertTrue(self.onboard()[0])
        ok, message, lifecycle = tenant_lifecycle.suspend_tenant('hardening')
        self.assertTrue(ok, message)
        self.assertEqual(lifecycle.current_status, 'inactive')
        self.assertIsNone(tenant_context.resolve_tenant('hardening.example.com'))
        summary = next(item for item in tenant_admin_dashboard.list_tenant_summaries() if item.slug == 'hardening')
        self.assertEqual(summary.status, 'inactive')

    def test_reactivation_restores_domain_and_dashboard_state(self):
        self.assertTrue(self.onboard()[0])
        self.assertTrue(tenant_lifecycle.suspend_tenant('hardening')[0])
        ok, message, lifecycle = tenant_lifecycle.reactivate_tenant('hardening')
        self.assertTrue(ok, message)
        self.assertEqual(lifecycle.current_status, 'active')
        self.assertEqual(tenant_context.resolve_tenant('hardening.example.com').slug, 'hardening')
        summary = next(item for item in tenant_admin_dashboard.list_tenant_summaries() if item.slug == 'hardening')
        self.assertEqual(summary.status, 'active')

    def test_archive_preserves_admin_visibility_without_public_resolution(self):
        self.assertTrue(self.onboard()[0])
        ok, message, lifecycle = tenant_lifecycle.archive_tenant('hardening')
        self.assertTrue(ok, message)
        self.assertEqual(lifecycle.current_status, 'archived')
        self.assertIsNone(tenant_context.resolve_tenant('hardening.example.com'))
        summary = next(item for item in tenant_admin_dashboard.list_tenant_summaries() if item.slug == 'hardening')
        self.assertEqual(summary.status, 'archived')
        self.assertEqual(summary.site_name, 'Hardening Brand')

    def test_dashboard_totals_include_onboarded_tenant_and_owner(self):
        before = tenant_admin_dashboard.get_dashboard_totals()
        self.assertTrue(self.onboard()[0])
        after = tenant_admin_dashboard.get_dashboard_totals()
        self.assertEqual(after['tenants'], before['tenants'] + 1)
        self.assertEqual(after['active_tenants'], before['active_tenants'] + 1)
        self.assertEqual(after['users'], before['users'] + 1)

    def test_primary_tenant_remains_protected_after_full_workflow(self):
        self.assertTrue(self.onboard()[0])
        self.assertFalse(tenant_lifecycle.suspend_tenant('solutions')[0])
        self.assertFalse(tenant_lifecycle.archive_tenant('solutions')[0])
        self.assertEqual(
            tenant_context.resolve_tenant(tenant_auth.PRIMARY_DOMAIN).slug,
            'solutions',
        )


if __name__ == '__main__':
    unittest.main()
