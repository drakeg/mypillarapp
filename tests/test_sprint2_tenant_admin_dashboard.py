from pathlib import Path
import importlib
import sys
import tempfile
import unittest

SITE_DIR = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SITE_DIR) not in sys.path:
    sys.path.insert(0, str(SITE_DIR))

import messaging
import tenant_admin_dashboard
import tenant_auth
import tenant_branding
import tenant_context
import tenant_conversations
import tenant_lifecycle
import tenant_organizations


class Sprint2TenantAdminDashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        messaging.DATA_DIR = data
        messaging.DB_PATH = data / 'madmallard.sqlite3'
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        importlib.reload(tenant_context)
        importlib.reload(tenant_conversations)
        importlib.reload(tenant_organizations)
        importlib.reload(tenant_branding)
        importlib.reload(tenant_lifecycle)
        importlib.reload(tenant_admin_dashboard)

    def tearDown(self):
        self.tmp.cleanup()

    def create_tenant(self):
        ok, message = tenant_organizations.create_organization(
            slug='dashboard-test',
            name='Dashboard Test',
            primary_domain='dashboard.example.com',
        )
        self.assertTrue(ok, message)

    def test_summaries_include_all_tenants(self):
        self.create_tenant()
        slugs = {item.slug for item in tenant_admin_dashboard.list_tenant_summaries()}
        self.assertIn('solutions', slugs)
        self.assertIn('dashboard-test', slugs)

    def test_summary_counts_are_tenant_scoped(self):
        self.create_tenant()
        tenant_conversations.create_conversation(
            tenant_slug='dashboard-test', kind='project_request', name='Test',
            email='test@example.com', subject='Request', body='Help',
        )
        tenant_conversations.create_conversation(
            tenant_slug='solutions', kind='chat', name='Other',
            email='other@example.com', subject='Chat', body='Hello',
        )
        summary = next(
            item for item in tenant_admin_dashboard.list_tenant_summaries()
            if item.slug == 'dashboard-test'
        )
        self.assertEqual(summary.conversation_count, 1)
        self.assertEqual(summary.project_request_count, 1)

    def test_summary_uses_tenant_branding(self):
        self.create_tenant()
        self.assertTrue(tenant_branding.update_branding(
            'dashboard-test', site_name='Dashboard Brand',
            primary_color='#123456', secondary_color='#abcdef',
        )[0])
        summary = next(
            item for item in tenant_admin_dashboard.list_tenant_summaries()
            if item.slug == 'dashboard-test'
        )
        self.assertEqual(summary.site_name, 'Dashboard Brand')
        self.assertEqual(summary.primary_color, '#123456')

    def test_totals_aggregate_summaries(self):
        self.create_tenant()
        totals = tenant_admin_dashboard.get_dashboard_totals()
        self.assertGreaterEqual(totals['tenants'], 4)
        self.assertGreaterEqual(totals['active_tenants'], 4)

    def test_lifecycle_actions_delegate_to_service(self):
        self.create_tenant()
        self.assertTrue(tenant_admin_dashboard.change_status('dashboard-test', 'suspend')[0])
        self.assertTrue(tenant_admin_dashboard.change_status('dashboard-test', 'reactivate')[0])
        self.assertTrue(tenant_admin_dashboard.change_status('dashboard-test', 'archive')[0])
        self.assertFalse(tenant_admin_dashboard.change_status('dashboard-test', 'delete')[0])

    def test_rendered_dashboard_contains_tenant_data_and_actions(self):
        self.create_tenant()
        body = tenant_admin_dashboard.render_tenant_dashboard()
        self.assertIn('Dashboard Test', body)
        self.assertIn('dashboard.example.com', body)
        self.assertIn("data-tenant-action='suspend'", body)
        self.assertIn('Project requests', body)
        self.assertIn('Protected', body)


if __name__ == '__main__':
    unittest.main()
