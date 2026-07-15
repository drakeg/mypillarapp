#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
auth_path = root / 'site' / 'solutions' / 'tenant_auth.py'
server_path = root / 'site' / 'solutions' / 'server.py'
changelog_path = root / 'CHANGELOG.md'
test_path = root / 'tests' / 'test_sprint2_tenant_auth_links.py'

auth = auth_path.read_text(encoding='utf-8')

def replace_once(text: str, old: str, new: str) -> str:
    if old not in text:
        raise SystemExit(f'Expected source block not found:\n{old[:160]}')
    return text.replace(old, new, 1)

auth = replace_once(
    auth,
    "def public_url(path: str) -> str:\n    if not path.startswith('/'):\n        path = '/' + path\n    return f'https://{PRIMARY_DOMAIN}{path}'",
    "def public_url(path: str, host: str = '') -> str:\n    if not path.startswith('/'):\n        path = '/' + path\n    public_host = (host or PRIMARY_DOMAIN).strip().lower().rstrip('.')\n    if '://' in public_host:\n        public_host = public_host.split('://', 1)[1]\n    public_host = public_host.split('/', 1)[0].split(',', 1)[0].strip()\n    if not public_host:\n        public_host = PRIMARY_DOMAIN\n    return f'https://{public_host}{path}'",
)

auth = replace_once(
    auth,
    "def register_user(*, organization_slug: str, first_name: str, last_name: str, email: str, password: str) -> tuple[bool, str]:",
    "def register_user(*, organization_slug: str, first_name: str, last_name: str, email: str, password: str, public_host: str = '') -> tuple[bool, str]:",
)
auth = replace_once(
    auth,
    "verify_url = public_url(f'/verify-email/{quote(token)}')",
    "verify_url = public_url(f'/verify-email/{quote(token)}', public_host)",
)

auth = replace_once(
    auth,
    "def request_password_reset(email: str) -> None:\n    email = email.strip().lower()\n    with db() as conn:\n        user = conn.execute('SELECT * FROM auth_users WHERE lower(email) = lower(?) AND is_active = 1', (email,)).fetchone()",
    "def request_password_reset(email: str, organization_slug: str = '', public_host: str = '') -> None:\n    email = email.strip().lower()\n    organization_slug = organization_slug.strip().lower()\n    if not organization_slug:\n        return\n    with db() as conn:\n        user = conn.execute(\n            '''SELECT u.* FROM auth_users u\n               JOIN auth_organizations o ON o.id = u.organization_id\n               WHERE lower(u.email) = lower(?) AND u.is_active = 1\n                 AND o.slug = ? AND o.status = 'active' ''',\n            (email, organization_slug),\n        ).fetchone()",
)
auth = replace_once(
    auth,
    "reset_url = public_url(f'/reset-password/{quote(token)}')",
    "reset_url = public_url(f'/reset-password/{quote(token)}', public_host)",
)
auth_path.write_text(auth, encoding='utf-8')

server = server_path.read_text(encoding='utf-8')
server = replace_once(
    server,
    "                email=str(payload.get('email', '')).strip(),\n                password=password,\n            )",
    "                email=str(payload.get('email', '')).strip(),\n                password=password,\n                public_host=context.host,\n            )",
)
server = replace_once(
    server,
    "        if parsed.path == '/forgot-password':\n            tenant_auth.request_password_reset(str(payload.get('email', '')))\n            return html_response",
    "        if parsed.path == '/forgot-password':\n            tenant_auth.request_password_reset(\n                str(payload.get('email', '')),\n                organization_slug=context.tenant.slug,\n                public_host=context.host,\n            )\n            return html_response",
)
server_path.write_text(server, encoding='utf-8')

changelog = changelog_path.read_text(encoding='utf-8')
marker = '### Added\n'
entry = '- Tenant-specific verification and password-reset links with tenant-scoped reset lookup.\n'
if entry not in changelog:
    changelog = changelog.replace(marker, marker + '\n' + entry, 1)
changelog_path.write_text(changelog, encoding='utf-8')

test_path.write_text(r'''from __future__ import annotations

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
''', encoding='utf-8')

print('Applied S2-T07 tenant-aware authentication links.')
