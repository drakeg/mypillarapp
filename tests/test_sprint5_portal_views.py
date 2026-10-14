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
import portal_messaging
import portal_notifications
import portal_projects
import portal_tickets
import portal_views
import tenant_auth
import tenant_conversations


class Sprint5CustomerPortalViewTests(unittest.TestCase):
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
            self.user_ids = {}
            for email in ('customer@example.com', 'other@example.com'):
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
                uid = int(cur.lastrowid)
                conn.execute(
                    """INSERT INTO auth_memberships(
                           created_at,updated_at,user_id,organization_id,
                           role_id,status
                       ) VALUES(?,?,?,?,?,'active')""",
                    (ts, ts, uid, org['id'], role['id']),
                )
                self.user_ids[email] = uid
            conn.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def user(self, email='customer@example.com'):
        with tenant_auth.db() as conn:
            return conn.execute(
                """SELECT u.*, o.slug AS organization_slug,
                          o.name AS organization_name
                   FROM auth_users u
                   JOIN auth_organizations o ON o.id=u.organization_id
                   WHERE u.id=?""",
                (self.user_ids[email],),
            ).fetchone()

    def test_dashboard_contains_only_current_customer_visible_records(self):
        mine = portal_projects.create_project(
            'solutions',
            customer_user_id=self.user_ids['customer@example.com'],
            title='My Project',
        )
        portal_projects.create_project(
            'solutions',
            customer_user_id=self.user_ids['other@example.com'],
            title='Other Project',
        )
        portal_tickets.create_ticket(
            'solutions',
            customer_user_id=self.user_ids['customer@example.com'],
            project_id=mine.id,
            subject='Visible Ticket',
            visibility='customer',
        )
        portal_tickets.create_ticket(
            'solutions',
            customer_user_id=self.user_ids['customer@example.com'],
            project_id=mine.id,
            subject='Internal Ticket',
            visibility='internal',
        )
        portal_files.create_file(
            'solutions',
            customer_user_id=self.user_ids['customer@example.com'],
            project_id=mine.id,
            name='Visible File.pdf',
            source_type='storage_key',
            source_ref='customers/visible.pdf',
            visibility='customer',
        )
        portal_notifications.create_delivery(
            'solutions',
            customer_user_id=self.user_ids['customer@example.com'],
            channel='in_app',
            notification_type='project_update',
            subject='Project updated',
        )

        body = portal_views.render_dashboard(self.user())
        self.assertIn('My Project', body)
        self.assertNotIn('Other Project', body)
        self.assertNotIn('Internal Ticket', body)
        self.assertIn('/portal/history', body)
        self.assertIn('/portal/messages', body)

    def test_project_and_ticket_details_fail_closed_for_other_customer(self):
        mine = portal_projects.create_project(
            'solutions',
            customer_user_id=self.user_ids['customer@example.com'],
            title='Mine',
        )
        other = portal_projects.create_project(
            'solutions',
            customer_user_id=self.user_ids['other@example.com'],
            title='Private Other',
        )
        internal = portal_tickets.create_ticket(
            'solutions',
            customer_user_id=self.user_ids['customer@example.com'],
            project_id=mine.id,
            subject='Internal',
            visibility='internal',
        )
        self.assertIsNotNone(
            portal_views.render_project(self.user(), mine.id)
        )
        self.assertIsNone(
            portal_views.render_project(self.user(), other.id)
        )
        self.assertIsNone(
            portal_views.render_ticket(self.user(), internal.id)
        )

    def test_file_detail_hides_managed_storage_key(self):
        project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.user_ids['customer@example.com'],
            title='Files',
        )
        file = portal_files.create_file(
            'solutions',
            customer_user_id=self.user_ids['customer@example.com'],
            project_id=project.id,
            name='report.pdf',
            source_type='storage_key',
            source_ref='tenant/private/customer/report.pdf',
            visibility='customer',
            mime_type='application/pdf',
        )
        body = portal_views.render_file(self.user(), file.id)
        self.assertIn('report.pdf', body)
        self.assertIn('managed portal storage', body)
        self.assertNotIn('tenant/private/customer/report.pdf', body)

    def test_external_file_detail_exposes_only_valid_customer_url(self):
        file = portal_files.create_file(
            'solutions',
            customer_user_id=self.user_ids['customer@example.com'],
            name='external.pdf',
            source_type='external_url',
            source_ref='https://example.com/external.pdf',
            visibility='customer',
        )
        body = portal_views.render_file(self.user(), file.id)
        self.assertIn('https://example.com/external.pdf', body)
        self.assertIn('Open file', body)

    def test_portal_conversation_hides_internal_messages_and_uses_portal_reply_api(self):
        conversation = tenant_conversations.create_conversation(
            tenant_slug='solutions',
            kind='chat',
            name='Customer',
            email='customer@example.com',
            body='Initial visible message',
            subject='Portal thread',
        )
        tenant_conversations.add_message(
            'solutions',
            conversation['token'],
            body='Internal support note',
            sender='Support',
            sender_type='admin',
            internal=True,
        )
        body = portal_views.render_conversation(
            self.user(), conversation['token']
        )
        self.assertIn('Initial visible message', body)
        self.assertNotIn('Internal support note', body)
        self.assertIn(
            f'/api/portal/messages/{conversation["token"]}',
            body,
        )
        self.assertNotIn(
            f'/api/chat/{conversation["token"]}/messages',
            body,
        )

    def test_other_customer_conversation_is_not_rendered(self):
        conversation = tenant_conversations.create_conversation(
            tenant_slug='solutions',
            kind='chat',
            name='Other',
            email='other@example.com',
            body='Private conversation',
            subject='Other thread',
        )
        self.assertIsNone(
            portal_views.render_conversation(
                self.user(), conversation['token']
            )
        )


if __name__ == '__main__':
    unittest.main()
