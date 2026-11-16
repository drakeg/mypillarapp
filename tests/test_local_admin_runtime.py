from __future__ import annotations

from pathlib import Path
import sys
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import server


class FakeHandler:
    def __init__(self, path='/', client_ip='192.168.1.50'):
        self.path = path
        self.client_address = (client_ip, 54321)
        self.status = None
        self.headers = {}

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.headers[key] = value

    def end_headers(self):
        pass


class LocalAdminRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.root_mode = server.ROOT_MODE
        self.local_admin_mode = server.LOCAL_ADMIN_MODE

    def tearDown(self):
        server.ROOT_MODE = self.root_mode
        server.LOCAL_ADMIN_MODE = self.local_admin_mode

    def test_admin_root_redirects_to_site_management(self):
        server.ROOT_MODE = 'admin'
        handler = FakeHandler()
        server.Handler.do_GET(handler)
        self.assertEqual(303, handler.status)
        self.assertEqual('/admin/sites', handler.headers.get('Location'))

    def test_local_admin_accepts_private_and_loopback_only(self):
        server.LOCAL_ADMIN_MODE = True
        self.assertTrue(
            server.local_admin_is_authenticated(
                FakeHandler(client_ip='192.168.1.25')
            )
        )
        self.assertTrue(
            server.local_admin_is_authenticated(
                FakeHandler(client_ip='127.0.0.1')
            )
        )
        self.assertFalse(
            server.local_admin_is_authenticated(
                FakeHandler(client_ip='8.8.8.8')
            )
        )

    def test_local_admin_mode_is_explicit_opt_in(self):
        server.LOCAL_ADMIN_MODE = False
        self.assertFalse(
            server.local_admin_is_authenticated(
                FakeHandler(client_ip='192.168.1.25')
            )
        )


if __name__ == '__main__':
    unittest.main()
