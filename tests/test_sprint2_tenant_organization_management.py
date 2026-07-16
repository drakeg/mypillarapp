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
import tenant_organizations


class Sprint2TenantOrganizationManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        messaging.DATA_DIR = data
        messaging.DB_PATH = data / 'madmallard.sqlite3'
        importlib.reload(tenant_auth)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        importlib.reload(tenant_context)
        importlib.reload(tenant_organizations)

    def tearDown(self):
        self.tmp.cleanup()

    def create(self, slug='new-tenant', domain='new.example.com'):
        return tenant_organizations.create_organization(
            slug=slug, name='New Tenant', primary_domain=domain
        )

    def test_create_organization_with_primary_domain(self):
        self.assertTrue(self.create()[0])
        row = tenant_organizations.get_organization('new-tenant')
        self.assertEqual(row['name'], 'New Tenant')
        self.assertEqual(row['primary_domain'], 'new.example.com')
        self.assertEqual(tenant_context.resolve_tenant('new.example.com').slug, 'new-tenant')

    def test_duplicate_slug_is_rejected(self):
        self.assertTrue(self.create()[0])
        ok, _ = tenant_organizations.create_organization(
            slug='new-tenant', name='Duplicate', primary_domain='other.example.com'
        )
        self.assertFalse(ok)

    def test_domain_cannot_be_assigned_to_two_tenants(self):
        self.assertTrue(self.create()[0])
        ok, _ = tenant_organizations.create_organization(
            slug='other-tenant', name='Other', primary_domain='NEW.EXAMPLE.COM:443'
        )
        self.assertFalse(ok)

    def test_inactive_organization_no_longer_resolves(self):
        self.assertTrue(self.create()[0])
        self.assertTrue(
            tenant_organizations.update_organization('new-tenant', status='inactive')[0]
        )
        self.assertIsNone(tenant_context.resolve_tenant('new.example.com'))
        self.assertEqual(
            tenant_organizations.get_organization('new-tenant')['status'], 'inactive'
        )

    def test_list_can_exclude_inactive_organizations(self):
        self.assertTrue(self.create()[0])
        tenant_organizations.update_organization('new-tenant', status='inactive')
        active = {
            row['slug']
            for row in tenant_organizations.list_organizations(include_inactive=False)
        }
        all_slugs = {row['slug'] for row in tenant_organizations.list_organizations()}
        self.assertNotIn('new-tenant', active)
        self.assertIn('new-tenant', all_slugs)

    def test_primary_domain_change_rejects_cross_tenant_conflict(self):
        self.assertTrue(self.create()[0])
        self.assertTrue(
            tenant_organizations.set_primary_domain(
                'new-tenant', 'replacement.example.com'
            )[0]
        )
        self.assertEqual(
            tenant_organizations.get_organization('new-tenant')['primary_domain'],
            'replacement.example.com',
        )
        tenant_organizations.create_organization(
            slug='other-tenant', name='Other', primary_domain='other.example.com'
        )
        self.assertFalse(
            tenant_organizations.set_primary_domain(
                'new-tenant', 'other.example.com'
            )[0]
        )


if __name__ == '__main__':
    unittest.main()
