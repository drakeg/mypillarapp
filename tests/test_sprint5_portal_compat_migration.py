from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import messaging
import portal_compat_migration
import portal_messaging
import portal_projects
import tenant_auth
import tenant_conversations


class Sprint5PortalCompatibilityMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        messaging.DATA_DIR = data
        messaging.DB_PATH = data / 'madmallard.sqlite3'
        self.customer_id = self._customer('solutions', 'customer@example.com')

    def tearDown(self):
        self.tmp.cleanup()

    def _customer(self, slug, email):
        with tenant_auth.db() as conn:
            org = conn.execute(
                'SELECT id FROM auth_organizations WHERE slug=?',
                (slug,),
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
                    ts, ts, org['id'], email, 'Portal', 'Customer',
                    tenant_auth.hash_password('abcdefghijkl'), 'viewer',
                ),
            )
            user_id = int(cur.lastrowid)
            conn.execute(
                """INSERT INTO auth_memberships(
                       created_at,updated_at,user_id,organization_id,
                       role_id,status
                   ) VALUES(?,?,?,?,?,'active')""",
                (ts, ts, user_id, org['id'], role['id']),
            )
            conn.commit()
        return user_id

    def _conversation(self, email='customer@example.com', kind='project_request'):
        return tenant_conversations.create_conversation(
            tenant_slug='solutions',
            kind=kind,
            name='Customer',
            email=email,
            body='Legacy history',
            subject='Existing request',
        )

    def test_safe_existing_history_is_linked_without_rewriting_source(self):
        conversation = self._conversation()
        with tenant_auth.db() as conn:
            before = tuple(conn.execute(
                '''
                SELECT token,kind,email,subject,status,created_at,updated_at
                FROM conversations WHERE token=?
                ''',
                (conversation['token'],),
            ).fetchone())

        result = portal_compat_migration.migrate_existing_customer_history()
        self.assertEqual(1, result.conversations_linked)
        self.assertEqual(0, result.already_linked)
        links = portal_messaging.list_links(
            'solutions',
            customer_user_id=self.customer_id,
        )
        self.assertEqual(1, len(links))
        self.assertEqual(conversation['token'], links[0].conversation_token)

        with tenant_auth.db() as conn:
            after = tuple(conn.execute(
                '''
                SELECT token,kind,email,subject,status,created_at,updated_at
                FROM conversations WHERE token=?
                ''',
                (conversation['token'],),
            ).fetchone())
        self.assertEqual(before, after)

    def test_second_run_is_idempotent(self):
        self._conversation()
        first = portal_compat_migration.migrate_existing_customer_history()
        second = portal_compat_migration.migrate_existing_customer_history()
        self.assertEqual(1, first.conversations_linked)
        self.assertEqual(0, second.conversations_linked)
        self.assertEqual(1, second.already_linked)
        self.assertEqual(1, len(portal_messaging.list_links('solutions')))

    def test_existing_portal_link_is_never_overwritten(self):
        conversation = self._conversation()
        project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.customer_id,
            title='Owner linked project',
        )
        existing = portal_messaging.link_conversation(
            'solutions',
            conversation['token'],
            customer_user_id=self.customer_id,
            project_id=project.id,
        )

        result = portal_compat_migration.migrate_existing_customer_history()
        self.assertEqual(0, result.conversations_linked)
        self.assertEqual(1, result.already_linked)
        current = portal_messaging.list_links(
            'solutions',
            customer_user_id=self.customer_id,
        )[0]
        self.assertEqual(existing.id, current.id)
        self.assertEqual(project.id, current.project_id)

    def test_unmatched_customer_remains_on_legacy_compatibility_path(self):
        conversation = self._conversation(email='unknown@example.com')
        result = portal_compat_migration.migrate_existing_customer_history()
        self.assertEqual(0, result.conversations_linked)
        self.assertEqual(1, result.unmatched_customers)
        self.assertIsNotNone(
            tenant_conversations.get_conversation(
                'solutions', conversation['token']
            )
        )
        self.assertEqual([], portal_messaging.list_links('solutions'))

    def test_revoked_customer_is_not_linked(self):
        conversation = self._conversation()
        with tenant_auth.db() as conn:
            conn.execute(
                """UPDATE auth_memberships SET status='revoked'
                   WHERE user_id=?""",
                (self.customer_id,),
            )
            conn.commit()
        result = portal_compat_migration.migrate_existing_customer_history()
        self.assertEqual(0, result.conversations_linked)
        self.assertEqual(1, result.unmatched_customers)
        self.assertIsNotNone(
            tenant_conversations.get_conversation(
                'solutions', conversation['token']
            )
        )

    def test_unsafe_legacy_audit_blocks_before_link_creation(self):
        self._conversation()
        with tenant_auth.db() as conn:
            conn.execute(
                """INSERT INTO conversations(
                       created_at,updated_at,token,kind,status,priority,
                       organization_slug,name,email,subject
                   ) VALUES(1,1,'bad-token','chat','new','normal',
                            'solutions','Bad','','Bad')"""
            )
            conn.commit()
        with self.assertRaisesRegex(ValueError, 'not safe to migrate'):
            portal_compat_migration.migrate_existing_customer_history()
        self.assertEqual([], portal_messaging.list_links('solutions'))


if __name__ == '__main__':
    unittest.main()
