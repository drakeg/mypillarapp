#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / 'site/solutions/server.py'
TEST = ROOT / 'tests/test_sprint2_server_request_context.py'
CHANGELOG = ROOT / 'CHANGELOG.md'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new, 1)


server = SERVER.read_text(encoding='utf-8')
server = replace_once(
    server,
    'import tenant_auth\n',
    'import tenant_auth\nimport request_context\n',
    'request_context import',
)

server = replace_once(
    server,
    "def public_account_nav(handler: BaseHTTPRequestHandler) -> str:\n    user = tenant_auth.current_user(get_cookie(handler, tenant_auth.SESSION_COOKIE))\n",
    "def public_account_nav(handler: BaseHTTPRequestHandler) -> str:\n    context = request_context.build_request_context(\n        handler.headers,\n        get_cookie(handler, tenant_auth.SESSION_COOKIE),\n    )\n    user = context.user if context else None\n",
    'tenant-aware public account nav',
)

server = replace_once(
    server,
    "    def _send_file(self, path: Path, content_type: str | None = None):\n",
    "    def request_context(self):\n        return request_context.build_request_context(\n            self.headers,\n            get_cookie(self, tenant_auth.SESSION_COOKIE),\n        )\n\n    def require_public_tenant(self, path: str):\n        if path.startswith('/admin') or path.startswith('/assets/'):\n            return True, None\n        context = self.request_context()\n        if context is None:\n            html_response(\n                self,\n                421,\n                '<h1>Unknown site</h1><p>This host is not configured for an active tenant.</p>',\n            )\n            return False, None\n        return True, context\n\n    def _send_file(self, path: Path, content_type: str | None = None):\n",
    'handler request context helpers',
)

server = replace_once(
    server,
    "        query = parse_qs(parsed.query)\n\n        if path == '/api/form-config':\n",
    "        query = parse_qs(parsed.query)\n        allowed, context = self.require_public_tenant(path)\n        if not allowed:\n            return\n\n        if path == '/api/form-config':\n",
    'GET tenant guard',
)

server = replace_once(
    server,
    "        payload = read_body(self)\n\n        if parsed.path == '/register':\n",
    "        payload = read_body(self)\n        allowed, context = self.require_public_tenant(parsed.path)\n        if not allowed:\n            return\n\n        if parsed.path == '/register':\n",
    'POST tenant guard',
)

for old in [
    "            user = tenant_auth.current_user(get_cookie(self, tenant_auth.SESSION_COOKIE))\n",
    "            user = tenant_auth.current_user(get_cookie(self, tenant_auth.SESSION_COOKIE))\n",
    "            user = tenant_auth.current_user(get_cookie(self, tenant_auth.SESSION_COOKIE))\n",
    "            user = tenant_auth.current_user(get_cookie(self, tenant_auth.SESSION_COOKIE))\n",
    "            user = tenant_auth.current_user(get_cookie(self, tenant_auth.SESSION_COOKIE))\n",
]:
    if old not in server:
        raise SystemExit('expected customer GET authentication lookup not found')
    server = server.replace(old, "            user = context.user if context else None\n", 1)

server = replace_once(
    server,
    "            session_token = get_cookie(self, tenant_auth.SESSION_COOKIE)\n            user = tenant_auth.current_user(session_token)\n",
    "            session_token = get_cookie(self, tenant_auth.SESSION_COOKIE)\n            user = context.user if context else None\n",
    'POST profile tenant authentication',
)

server = replace_once(
    server,
    "                organization_slug=str(payload.get('organization', '')).strip(),\n",
    "                organization_slug=context.tenant.slug,\n",
    'tenant-bound registration',
)

server = replace_once(
    server,
    "        if parsed.path == '/login':\n            ok, message, session = tenant_auth.login_user(str(payload.get('email', '')), str(payload.get('password', '')))\n            if ok:\n                return redirect(self, '/dashboard', {'Set-Cookie': tenant_auth.session_cookie(session)})\n            return html_response(self, 403, tenant_auth.render_login(message, True))\n",
    "        if parsed.path == '/login':\n            ok, message, session = tenant_auth.login_user(\n                str(payload.get('email', '')),\n                str(payload.get('password', '')),\n            )\n            if ok:\n                user = tenant_auth.current_user(session)\n                if request_context.user_belongs_to_tenant(user, context.tenant):\n                    return redirect(\n                        self,\n                        '/dashboard',\n                        {'Set-Cookie': tenant_auth.session_cookie(session)},\n                    )\n                tenant_auth.logout_session(session)\n                message = 'Invalid email or password.'\n            return html_response(self, 403, tenant_auth.render_login(message, True))\n",
    'tenant-bound login',
)

SERVER.write_text(server, encoding='utf-8')

TEST.write_text('''from __future__ import annotations

import importlib
from pathlib import Path
import sys
import unittest
from unittest import mock

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import request_context
import server


class FakeHandler:
    def __init__(self, headers=None, cookies=''):
        self.headers = headers or {}
        if cookies:
            self.headers['Cookie'] = cookies


class Sprint2ServerRequestContextTests(unittest.TestCase):
    def test_public_navigation_hides_cross_tenant_user(self):
        tenant = mock.Mock(slug='solutions')
        context = request_context.RequestContext(tenant=tenant, host='pillar.madmallards.com', user=None)
        with mock.patch.object(request_context, 'build_request_context', return_value=context):
            nav = server.public_account_nav(FakeHandler({'Host': 'pillar.madmallards.com'}))
        self.assertIn('Sign In', nav)
        self.assertNotIn('Logout', nav)

    def test_public_navigation_shows_matching_tenant_user(self):
        tenant = mock.Mock(slug='solutions')
        user = {'first_name': 'Greg', 'email': 'greg@example.com'}
        context = request_context.RequestContext(tenant=tenant, host='pillar.madmallards.com', user=user)
        with mock.patch.object(request_context, 'build_request_context', return_value=context):
            nav = server.public_account_nav(FakeHandler({'Host': 'pillar.madmallards.com'}))
        self.assertIn('Greg', nav)
        self.assertIn('Logout', nav)

    def test_server_uses_tenant_slug_for_registration(self):
        source = (SOLUTIONS / 'server.py').read_text(encoding='utf-8')
        self.assertIn('organization_slug=context.tenant.slug', source)
        self.assertNotIn("organization_slug=str(payload.get('organization'", source)

    def test_server_rejects_unknown_public_hosts(self):
        source = (SOLUTIONS / 'server.py').read_text(encoding='utf-8')
        self.assertIn("html_response(\\n                self,\\n                421,", source)
        self.assertIn("allowed, context = self.require_public_tenant(path)", source)
        self.assertIn("allowed, context = self.require_public_tenant(parsed.path)", source)

    def test_login_checks_authenticated_user_tenant(self):
        source = (SOLUTIONS / 'server.py').read_text(encoding='utf-8')
        self.assertIn('request_context.user_belongs_to_tenant(user, context.tenant)', source)
        self.assertIn('tenant_auth.logout_session(session)', source)


if __name__ == '__main__':
    unittest.main()
''', encoding='utf-8')

changelog = CHANGELOG.read_text(encoding='utf-8')
entry = '- HTTP request handling now enforces active tenant hosts and tenant-scoped customer sessions.\n'
if entry not in changelog:
    changelog = changelog.replace('### Added\n\n', f'### Added\n\n{entry}', 1)
    CHANGELOG.write_text(changelog, encoding='utf-8')

print('Applied S2-T03 tenant-aware server request handling.')
