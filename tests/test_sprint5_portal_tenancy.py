from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import messaging
import portal_tenancy
import tenant_auth
import tenant_conversations


class Sprint5PortalBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        messaging.DATA_DIR = data
        messaging.DB_PATH = data / 'madmallard.sqlite3'

        with tenant_auth.db() as conn:
            org = conn.execute(
                "SELECT id FROM auth_organizations WHERE slug='solutions'"
            ).fetchone()
            role = conn.execute(
                "SELECT id FROM auth_roles WHERE slug='viewer'"
            ).fetchone()
            ts = tenant_auth.now()
            cur = conn.execute(
                """INSERT INTO auth_users(
                       created_at,updated_at,organization_id,email,
                       first_name,last_name,password_hash,role,is_active
                   ) VALUES(?,?,?,?,?,?,?,?,1)""",
                (
                    ts, ts, org['id'], 'customer@example.com',
                    'Portal', 'Customer',
                    tenant_auth.hash_password('abcdefghijkl'),
                    'viewer'
                ),
            )
            self.user_id = int(cur.lastrowid)
            conn.execute(
                """INSERT INTO auth_memberships(
                       created_at,updated_at,user_id,organization_id,role_id,status
                   ) VALUES(?,?,?,?,?,'active')""",
                (ts, ts, self.user_id, org['id'], role['id']),
            )
            conn.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def current_user(self):
        with tenant_auth.db() as conn:
            return conn.execute(
                """SELECT u.*, o.slug AS organization_slug,
                          o.name AS organization_name
                   FROM auth_users u
                   JOIN auth_organizations o ON o.id=u.organization_id
                   WHERE u.id=?""",
                (self.user_id,),
            ).fetchone()

    def test_customer_scope_requires_active_user_membership_and_tenant(self):
        scope = portal_tenancy.customer_scope(self.current_user())
        self.assertEqual('solutions', scope.organization_slug)
        self.assertEqual('customer@example.com', scope.email)

        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_memberships SET status='revoked' WHERE user_id=?",
                (self.user_id,),
            )
            conn.commit()
        with self.assertRaises(ValueError):
            portal_tenancy.customer_scope(self.current_user())

    def test_history_is_scoped_by_tenant_and_customer_email(self):
        scope = portal_tenancy.customer_scope(self.current_user())
        mine = tenant_conversations.create_conversation(
            tenant_slug='solutions', kind='project_request',
            name='Portal Customer', email='customer@example.com',
            body='Mine', subject='Mine'
        )
        tenant_conversations.create_conversation(
            tenant_slug='solutions', kind='project_request',
            name='Other', email='other@example.com',
            body='Other', subject='Other'
        )
        tenant_conversations.create_conversation(
            tenant_slug='adventures', kind='project_request',
            name='Portal Customer', email='customer@example.com',
            body='Foreign tenant', subject='Foreign tenant'
        )

        history = portal_tenancy.list_customer_history(
            scope, kind='project_request'
        )
        self.assertEqual([mine['token']], [row['token'] for row in history])

    def test_foreign_or_other_customer_token_fails_closed(self):
        scope = portal_tenancy.customer_scope(self.current_user())
        other = tenant_conversations.create_conversation(
            tenant_slug='solutions', kind='chat',
            name='Other', email='other@example.com',
            body='Private'
        )
        foreign = tenant_conversations.create_conversation(
            tenant_slug='adventures', kind='chat',
            name='Portal Customer', email='customer@example.com',
            body='Foreign'
        )
        self.assertIsNone(
            portal_tenancy.conversation_for_customer(scope, other['token'])
        )
        self.assertIsNone(
            portal_tenancy.conversation_for_customer(scope, foreign['token'])
        )

    def test_legacy_history_audit_detects_missing_identity_and_unknown_tenant(self):
        tenant_conversations.create_conversation(
            tenant_slug='solutions', kind='project_request',
            name='Known', email='customer@example.com',
            body='Known'
        )
        tenant_conversations.create_conversation(
            tenant_slug='solutions', kind='chat',
            name='No email', email='', body='Anonymous'
        )
        tenant_conversations.create_conversation(
            tenant_slug='unknown-brand', kind='chat',
            name='Unknown', email='unknown@example.com', body='Unknown'
        )

        audit = portal_tenancy.audit_existing_customer_history()
        self.assertEqual(3, audit.conversations)
        self.assertEqual(1, audit.project_requests)
        self.assertEqual(2, audit.chats)
        self.assertEqual(1, audit.missing_customer_email)
        self.assertEqual(1, audit.unknown_organization_rows)
        self.assertFalse(audit.safe_for_portal_foundation)

    def test_clean_history_audit_is_safe(self):
        tenant_conversations.create_conversation(
            tenant_slug='solutions', kind='project_request',
            name='Known', email='customer@example.com', body='Known'
        )
        audit = portal_tenancy.audit_existing_customer_history()
        self.assertTrue(audit.safe_for_portal_foundation)


if __name__ == '__main__':
    unittest.main()
