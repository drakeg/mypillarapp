from __future__ import annotations

import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SITE_DIR = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SITE_DIR) not in sys.path:
    sys.path.insert(0, str(SITE_DIR))

import messaging
import tenant_auth


class Sprint2TenantAuthLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        messaging.DATA_DIR = data_dir
        messaging.DB_PATH = data_dir / 'madmallard.sqlite3'
        tenant_auth.DATA_DIR = data_dir
        tenant_auth.DB_PATH = data_dir / 'madmallard.sqlite3'
        importlib.reload(tenant_auth)
        tenant_auth.DATA_DIR = data_dir
        tenant_auth.DB_PATH = data_dir / 'madmallard.sqlite3'

    def tearDown(self):
        self.temp_dir.cleanup()

    def register(self, host='client.example.com'):
        sent = []
        with patch.object(messaging, 'send_email', side_effect=lambda *args: sent.append(args) or True):
            result = tenant_auth.register_user(
                organization_slug='solutions',
                first_name='Test',
                last_name='Customer',
                email='customer@example.com',
                password='very-secure-password',
                public_host=host,
            )
        return result, sent

    def activate_user(self):
        self.register()
        with tenant_auth.db() as conn:
            conn.execute('UPDATE auth_users SET is_active = 1')
            conn.commit()

    def test_public_url_uses_requested_tenant_host(self):
        self.assertEqual(
            tenant_auth.public_url('/login', 'Client.Example.com.'),
            'https://client.example.com/login',
        )

    def test_registration_verification_link_uses_tenant_host(self):
        (ok, _), sent = self.register('solutions.example.com')
        self.assertTrue(ok)
        self.assertEqual(len(sent), 1)
        self.assertIn('https://solutions.example.com/verify-email/', sent[0][1])

    def test_password_reset_is_scoped_to_tenant(self):
        self.activate_user()
        sent = []
        with patch.object(messaging, 'send_email', side_effect=lambda *args: sent.append(args) or True):
            tenant_auth.request_password_reset(
                'customer@example.com',
                organization_slug='adventures',
                public_host='adventures.example.com',
            )
        self.assertEqual(sent, [])

    def test_password_reset_link_uses_matching_tenant_host(self):
        self.activate_user()
        sent = []
        with patch.object(messaging, 'send_email', side_effect=lambda *args: sent.append(args) or True):
            tenant_auth.request_password_reset(
                'customer@example.com',
                organization_slug='solutions',
                public_host='solutions.example.com',
            )
        self.assertEqual(len(sent), 1)
        self.assertIn('https://solutions.example.com/reset-password/', sent[0][1])

    def test_server_passes_resolved_tenant_to_auth_email_flows(self):
        source = (SITE_DIR / 'server.py').read_text(encoding='utf-8')
        self.assertIn('public_host=context.host', source)
        self.assertIn('organization_slug=context.tenant.slug', source)
        self.assertNotIn("request_password_reset(str(payload.get('email', '')))", source)


if __name__ == '__main__':
    unittest.main()
