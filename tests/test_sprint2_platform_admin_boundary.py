from http.cookies import SimpleCookie
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

SITE_DIR = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SITE_DIR) not in sys.path:
    sys.path.insert(0, str(SITE_DIR))

import server


class Sprint2PlatformAdminBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.original = (
            server.ADMIN_USERNAME,
            server.ADMIN_PASSWORD_HASH,
            server.ADMIN_SESSION_SECRET,
            server.ADMIN_TOKEN,
        )
        server.ADMIN_USERNAME = 'platform-admin'
        server.ADMIN_PASSWORD_HASH = 'configured'
        server.ADMIN_SESSION_SECRET = 'test-platform-secret'
        server.ADMIN_TOKEN = 'emergency-platform-token'

    def tearDown(self):
        (
            server.ADMIN_USERNAME,
            server.ADMIN_PASSWORD_HASH,
            server.ADMIN_SESSION_SECRET,
            server.ADMIN_TOKEN,
        ) = self.original

    def handler_with_cookie(self, name: str, value: str):
        cookie = SimpleCookie()
        cookie[name] = value
        return SimpleNamespace(
            headers={'Cookie': cookie.output(header='', sep='').strip()}
        )

    def test_platform_session_contains_explicit_scope(self):
        token = server.make_admin_session('platform-admin')
        self.assertTrue(
            server.verify_admin_session(
                token,
                server.PLATFORM_ADMIN_SCOPE,
            )
        )

    def test_wrong_scope_is_rejected_for_platform_admin(self):
        token = server.make_admin_session(
            'platform-admin',
            scope='tenant_admin',
        )
        self.assertTrue(server.verify_admin_session(token))
        self.assertFalse(
            server.verify_admin_session(
                token,
                server.PLATFORM_ADMIN_SCOPE,
            )
        )

    def test_platform_guard_accepts_platform_scoped_cookie(self):
        token = server.make_admin_session('platform-admin')
        handler = self.handler_with_cookie('mms_admin_session', token)
        self.assertTrue(server.platform_admin_is_authenticated(handler))

    def test_customer_cookie_does_not_grant_platform_admin(self):
        handler = self.handler_with_cookie(
            'mmp_user_session',
            'customer-session-token',
        )
        self.assertFalse(server.platform_admin_is_authenticated(handler))

    def test_platform_emergency_token_remains_available(self):
        handler = SimpleNamespace(headers={})
        self.assertTrue(
            server.platform_admin_is_authenticated(
                handler,
                {'token': ['emergency-platform-token']},
            )
        )

    def test_platform_session_still_authorizes_operational_admin(self):
        token = server.make_admin_session('platform-admin')
        handler = self.handler_with_cookie('mms_admin_session', token)
        self.assertTrue(server.admin_is_authenticated(handler))


if __name__ == '__main__':
    unittest.main()
