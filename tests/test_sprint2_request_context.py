from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOLUTIONS = ROOT / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import request_context
import tenant_auth
import tenant_context


class Sprint2RequestContextTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / 'request-context.sqlite3'
        self.auth_data_dir = tenant_auth.DATA_DIR
        self.auth_db_path = tenant_auth.DB_PATH
        tenant_auth.DATA_DIR = Path(self.tempdir.name)
        tenant_auth.DB_PATH = self.db_path
        tenant_context.ensure_schema()
        tenant_context.register_domain('personal-training', 'fitness.example.test', primary=True)
        with tenant_auth.db() as conn:
            conn.execute("UPDATE auth_organizations SET status='active' WHERE slug='personal-training'")
            conn.commit()

    def tearDown(self):
        tenant_auth.DATA_DIR = self.auth_data_dir
        tenant_auth.DB_PATH = self.auth_db_path
        self.tempdir.cleanup()

    def test_forwarded_host_takes_precedence(self):
        headers = {
            'Host': 'internal-app:8000',
            'X-Forwarded-Host': 'PILLAR.MADMALLARDS.COM:443',
        }
        self.assertEqual(request_context.request_host(headers), 'pillar.madmallards.com')
        self.assertEqual(request_context.resolve_request_tenant(headers).slug, 'solutions')

    def test_first_forwarded_host_is_used(self):
        headers = {'X-Forwarded-Host': 'fitness.example.test, proxy.internal'}
        self.assertEqual(request_context.request_host(headers), 'fitness.example.test')
        self.assertEqual(request_context.resolve_request_tenant(headers).slug, 'personal-training')

    def test_unknown_host_has_no_request_context(self):
        self.assertIsNone(request_context.build_request_context({'Host': 'unknown.example.test'}))

    def test_matching_tenant_session_is_authenticated(self):
        user = {'organization_slug': 'solutions', 'email': 'owner@example.test'}
        with patch.object(tenant_auth, 'current_user', return_value=user):
            context = request_context.build_request_context(
                {'Host': 'pillar.madmallards.com'},
                'session-token',
            )
        self.assertIsNotNone(context)
        self.assertTrue(context.authenticated)
        self.assertEqual(context.user['email'], 'owner@example.test')

    def test_cross_tenant_session_is_treated_as_anonymous(self):
        user = {'organization_slug': 'personal-training', 'email': 'coach@example.test'}
        with patch.object(tenant_auth, 'current_user', return_value=user):
            context = request_context.build_request_context(
                {'Host': 'pillar.madmallards.com'},
                'session-token',
            )
        self.assertIsNotNone(context)
        self.assertFalse(context.authenticated)
        self.assertIsNone(context.user)

    def test_missing_session_does_not_call_authentication(self):
        with patch.object(tenant_auth, 'current_user') as current_user:
            context = request_context.build_request_context({'Host': 'pillar.madmallards.com'})
        current_user.assert_not_called()
        self.assertIsNotNone(context)
        self.assertFalse(context.authenticated)


if __name__ == '__main__':
    unittest.main()
