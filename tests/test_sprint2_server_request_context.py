from __future__ import annotations

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
        self.assertIn("html_response(\n                self,\n                421,", source)
        self.assertIn("allowed, context = self.require_public_tenant(path)", source)
        self.assertIn("allowed, context = self.require_public_tenant(parsed.path)", source)

    def test_login_checks_authenticated_user_tenant(self):
        source = (SOLUTIONS / 'server.py').read_text(encoding='utf-8')
        self.assertIn('request_context.user_belongs_to_tenant(user, context.tenant)', source)
        self.assertIn('tenant_auth.logout_session(session)', source)


if __name__ == '__main__':
    unittest.main()
