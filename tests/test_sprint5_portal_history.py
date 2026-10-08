from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import messaging
import portal_files
import portal_history
import portal_notifications
import portal_projects
import portal_tenancy
import portal_tickets
import tenant_auth
import tenant_conversations


class Sprint5PortalHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        messaging.DATA_DIR = data
        messaging.DB_PATH = data / 'madmallard.sqlite3'

        with tenant_auth.db() as conn:
            ts = tenant_auth.now()
            role = conn.execute(
                "SELECT id FROM auth_roles WHERE slug='viewer'"
            ).fetchone()
            self.users = {}
            for slug, email in (
                ('solutions', 'customer@example.com'),
                ('adventures', 'traveler@example.com'),
            ):
                org = conn.execute(
                    'SELECT id FROM auth_organizations WHERE slug=?', (slug,)
                ).fetchone()
                cur = conn.execute(
                    """INSERT INTO auth_users(
                           created_at,updated_at,organization_id,email,
                           first_name,last_name,password_hash,role,is_active
                       ) VALUES(?,?,?,?,?,?,?,?,1)""",
                    (
                        ts, ts, org['id'], email, 'Portal', 'Customer',
                        tenant_auth.hash_password('abcdefghijkl'), 'viewer'
                    ),
                )
                uid = int(cur.lastrowid)
                conn.execute(
                    """INSERT INTO auth_memberships(
                           created_at,updated_at,user_id,organization_id,
                           role_id,status
                       ) VALUES(?,?,?,?,?,'active')""",
                    (ts, ts, uid, org['id'], role['id']),
                )
                self.users[slug] = uid
            conn.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def scope(self, slug='solutions'):
        with tenant_auth.db() as conn:
            row = conn.execute(
                """SELECT u.*, o.slug AS organization_slug
                   FROM auth_users u
                   JOIN auth_organizations o ON o.id=u.organization_id
                   WHERE u.id=?""",
                (self.users[slug],),
            ).fetchone()
        return portal_tenancy.customer_scope(row)

    def test_unified_history_includes_customer_visible_sources(self):
        project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.users['solutions'],
            title='Portal project',
        )
        visible_ticket = portal_tickets.create_ticket(
            'solutions',
            customer_user_id=self.users['solutions'],
            project_id=project.id,
            subject='Visible ticket',
            visibility='customer',
        )
        portal_tickets.create_ticket(
            'solutions',
            customer_user_id=self.users['solutions'],
            project_id=project.id,
            subject='Internal ticket',
            visibility='internal',
        )
        visible_file = portal_files.create_file(
            'solutions',
            customer_user_id=self.users['solutions'],
            project_id=project.id,
            name='guide.pdf',
            source_type='storage_key',
            source_ref='portal/guide.pdf',
            mime_type='application/pdf',
            visibility='customer',
        )
        portal_files.create_file(
            'solutions',
            customer_user_id=self.users['solutions'],
            project_id=project.id,
            name='internal.txt',
            source_type='storage_key',
            source_ref='portal/internal.txt',
            visibility='internal',
        )
        conversation = tenant_conversations.create_conversation(
            tenant_slug='solutions',
            kind='chat',
            name='Customer',
            email='customer@example.com',
            body='Hello',
            subject='Conversation',
        )
        delivery = portal_notifications.create_delivery(
            'solutions',
            customer_user_id=self.users['solutions'],
            channel='in_app',
            notification_type='service_notice',
            subject='Notice',
        )

        history = portal_history.list_customer_history(self.scope())
        seen = {(item.kind, item.record_id) for item in history}
        self.assertIn(('project', str(project.id)), seen)
        self.assertIn(('ticket', str(visible_ticket.id)), seen)
        self.assertIn(('file', str(visible_file.id)), seen)
        self.assertIn(('conversation', conversation['token']), seen)
        self.assertIn(('notification', str(delivery.id)), seen)
        self.assertNotIn(
            'Internal ticket', [item.title for item in history]
        )
        self.assertNotIn(
            'internal.txt', [item.title for item in history]
        )

    def test_foreign_customer_and_tenant_records_do_not_leak(self):
        portal_projects.create_project(
            'adventures',
            customer_user_id=self.users['adventures'],
            title='Foreign project',
        )
        tenant_conversations.create_conversation(
            tenant_slug='adventures',
            kind='chat',
            name='Traveler',
            email='traveler@example.com',
            body='Foreign',
            subject='Foreign conversation',
        )
        history = portal_history.list_customer_history(self.scope())
        titles = [item.title for item in history]
        self.assertNotIn('Foreign project', titles)
        self.assertNotIn('Foreign conversation', titles)

    def test_history_limit_is_bounded_and_enforced(self):
        for index in range(5):
            portal_projects.create_project(
                'solutions',
                customer_user_id=self.users['solutions'],
                title=f'Project {index}',
            )
        history = portal_history.list_customer_history(
            self.scope(), limit=3
        )
        self.assertEqual(3, len(history))
        with self.assertRaises(ValueError):
            portal_history.list_customer_history(self.scope(), limit=0)
        with self.assertRaises(ValueError):
            portal_history.list_customer_history(self.scope(), limit=501)

    def test_ordering_is_deterministic_for_equal_timestamps(self):
        first = portal_projects.create_project(
            'solutions',
            customer_user_id=self.users['solutions'],
            title='A',
        )
        second = portal_projects.create_project(
            'solutions',
            customer_user_id=self.users['solutions'],
            title='B',
        )
        with tenant_auth.db() as conn:
            conn.execute(
                'UPDATE portal_projects SET updated_at=1234567890 WHERE id IN (?,?)',
                (first.id, second.id),
            )
            conn.commit()

        one = portal_history.list_customer_history(self.scope())
        two = portal_history.list_customer_history(self.scope())
        self.assertEqual(one, two)

    def test_stale_scope_fails_after_membership_revocation(self):
        scope = self.scope()
        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_memberships SET status='revoked' WHERE user_id=?",
                (self.users['solutions'],),
            )
            conn.commit()
        with self.assertRaises(ValueError):
            portal_history.list_customer_history(scope)


if __name__ == '__main__':
    unittest.main()
