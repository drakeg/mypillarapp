from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import messaging
import portal_messaging
import portal_projects
import portal_tenancy
import portal_tickets
import tenant_auth
import tenant_conversations


class Sprint5PortalMessagingTests(unittest.TestCase):
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

    def conversation(self, slug='solutions', email='customer@example.com'):
        return tenant_conversations.create_conversation(
            tenant_slug=slug,
            kind='chat',
            name='Customer',
            email=email,
            body='Initial message',
            subject='Service thread',
        )

    def test_link_conversation_to_same_customer_project_and_ticket(self):
        conversation = self.conversation()
        project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.users['solutions'],
            title='Project',
        )
        ticket = portal_tickets.create_ticket(
            'solutions',
            customer_user_id=self.users['solutions'],
            project_id=project.id,
            subject='Ticket',
        )
        link = portal_messaging.link_conversation(
            'solutions',
            conversation['token'],
            customer_user_id=self.users['solutions'],
            project_id=project.id,
            ticket_id=ticket.id,
        )
        self.assertEqual(project.id, link.project_id)
        self.assertEqual(ticket.id, link.ticket_id)
        self.assertIsNotNone(
            tenant_conversations.get_conversation(
                'solutions', conversation['token']
            )
        )

    def test_relink_is_idempotent_and_unlink_is_non_destructive(self):
        conversation = self.conversation()
        first = portal_messaging.link_conversation(
            'solutions',
            conversation['token'],
            customer_user_id=self.users['solutions'],
        )
        project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.users['solutions'],
            title='Project',
        )
        second = portal_messaging.link_conversation(
            'solutions',
            conversation['token'],
            customer_user_id=self.users['solutions'],
            project_id=project.id,
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            1, len(portal_messaging.list_links('solutions'))
        )
        self.assertTrue(
            portal_messaging.unlink_conversation(
                'solutions', conversation['token']
            )
        )
        self.assertIsNotNone(
            tenant_conversations.get_conversation(
                'solutions', conversation['token']
            )
        )

    def test_foreign_or_other_customer_links_fail_closed(self):
        foreign = self.conversation(
            slug='adventures', email='traveler@example.com'
        )
        with self.assertRaises(ValueError):
            portal_messaging.link_conversation(
                'solutions',
                foreign['token'],
                customer_user_id=self.users['solutions'],
            )

        other = self._extra_customer('solutions', 'other@example.com')
        conversation = self.conversation()
        with self.assertRaisesRegex(ValueError, 'does not match'):
            portal_messaging.link_conversation(
                'solutions',
                conversation['token'],
                customer_user_id=other,
            )

    def test_project_ticket_customer_and_relationship_mismatch_rejected(self):
        other = self._extra_customer('solutions', 'other@example.com')
        conversation = self.conversation()
        project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.users['solutions'],
            title='Mine',
        )
        other_project = portal_projects.create_project(
            'solutions',
            customer_user_id=other,
            title='Other',
        )
        other_ticket = portal_tickets.create_ticket(
            'solutions',
            customer_user_id=other,
            project_id=other_project.id,
            subject='Other ticket',
        )
        with self.assertRaisesRegex(ValueError, 'ticket customer'):
            portal_messaging.link_conversation(
                'solutions',
                conversation['token'],
                customer_user_id=self.users['solutions'],
                ticket_id=other_ticket.id,
            )

        ticket = portal_tickets.create_ticket(
            'solutions',
            customer_user_id=self.users['solutions'],
            project_id=project.id,
            subject='Mine',
        )
        second_project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.users['solutions'],
            title='Second',
        )
        with self.assertRaisesRegex(ValueError, 'ticket project'):
            portal_messaging.link_conversation(
                'solutions',
                conversation['token'],
                customer_user_id=self.users['solutions'],
                project_id=second_project.id,
                ticket_id=ticket.id,
            )

    def test_internal_messages_are_hidden_from_customer_reads(self):
        conversation = self.conversation()
        tenant_conversations.add_message(
            'solutions',
            conversation['token'],
            body='Visible reply',
            sender='Support',
            sender_type='admin',
            internal=False,
        )
        tenant_conversations.add_message(
            'solutions',
            conversation['token'],
            body='Internal note',
            sender='Support',
            sender_type='admin',
            internal=True,
        )
        messages = portal_messaging.list_customer_messages(
            self.scope(), conversation['token']
        )
        bodies = [row['body'] for row in messages]
        self.assertIn('Initial message', bodies)
        self.assertIn('Visible reply', bodies)
        self.assertNotIn('Internal note', bodies)

    def test_authenticated_customer_reply_uses_tenant_safe_thread(self):
        conversation = self.conversation()
        result = portal_messaging.add_customer_reply(
            self.scope(),
            conversation['token'],
            body='Customer follow-up',
            sender='Portal Customer',
        )
        self.assertIsNotNone(result)
        messages = portal_messaging.list_customer_messages(
            self.scope(), conversation['token']
        )
        self.assertEqual('Customer follow-up', messages[-1]['body'])
        self.assertEqual('visitor', messages[-1]['sender_type'])

        foreign_scope = self.scope('adventures')
        self.assertIsNone(
            portal_messaging.add_customer_reply(
                foreign_scope,
                conversation['token'],
                body='Blocked',
            )
        )

    def test_stale_scope_fails_after_membership_revocation(self):
        conversation = self.conversation()
        scope = self.scope()
        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_memberships SET status='revoked' WHERE user_id=?",
                (self.users['solutions'],),
            )
            conn.commit()
        with self.assertRaises(ValueError):
            portal_messaging.list_customer_messages(
                scope, conversation['token']
            )
        with self.assertRaises(ValueError):
            portal_messaging.add_customer_reply(
                scope, conversation['token'], body='Blocked'
            )

    def test_revoked_customer_membership_fails_before_linking(self):
        conversation = self.conversation()
        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_memberships SET status='revoked' WHERE user_id=?",
                (self.users['solutions'],),
            )
            conn.commit()
        with self.assertRaises(ValueError):
            portal_messaging.link_conversation(
                'solutions',
                conversation['token'],
                customer_user_id=self.users['solutions'],
            )

    def _extra_customer(self, slug, email):
        with tenant_auth.db() as conn:
            org = conn.execute(
                'SELECT id FROM auth_organizations WHERE slug=?', (slug,)
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
                    ts, ts, org['id'], email, 'Other', 'Customer',
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
            conn.commit()
        return uid


if __name__ == '__main__':
    unittest.main()
