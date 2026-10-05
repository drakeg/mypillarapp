from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import portal_projects
import portal_tickets
import tenant_auth


class Sprint5PortalTicketTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
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

    def test_ticket_crud_and_project_linkage(self):
        project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.users['solutions'],
            title='Portal build',
        )
        ticket = portal_tickets.create_ticket(
            'solutions',
            customer_user_id=self.users['solutions'],
            project_id=project.id,
            subject='Need an update',
            description='Please share progress.',
            priority='high',
        )
        self.assertEqual(project.id, ticket.project_id)
        self.assertEqual('customer', ticket.visibility)
        updated = portal_tickets.update_ticket(
            'solutions', ticket.id,
            status='in_progress', priority='urgent'
        )
        self.assertEqual('in_progress', updated.status)
        self.assertEqual('urgent', updated.priority)

    def test_project_customer_mismatch_is_rejected(self):
        second = self._create_extra_customer('solutions', 'second@example.com')
        project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.users['solutions'],
            title='Private project',
        )
        with self.assertRaisesRegex(ValueError, 'does not match'):
            portal_tickets.create_ticket(
                'solutions',
                customer_user_id=second,
                project_id=project.id,
                subject='Blocked',
            )

    def test_foreign_project_and_customer_are_rejected(self):
        foreign_project = portal_projects.create_project(
            'adventures',
            customer_user_id=self.users['adventures'],
            title='Foreign',
        )
        with self.assertRaises(ValueError):
            portal_tickets.create_ticket(
                'solutions',
                customer_user_id=self.users['solutions'],
                project_id=foreign_project.id,
                subject='Blocked',
            )
        with self.assertRaises(ValueError):
            portal_tickets.create_ticket(
                'solutions',
                customer_user_id=self.users['adventures'],
                subject='Blocked',
            )

    def test_visibility_filters_customer_vs_internal(self):
        visible = portal_tickets.create_ticket(
            'solutions',
            customer_user_id=self.users['solutions'],
            subject='Visible',
            visibility='customer',
        )
        portal_tickets.create_ticket(
            'solutions',
            customer_user_id=self.users['solutions'],
            subject='Internal',
            visibility='internal',
        )
        self.assertEqual(
            [visible.id],
            [t.id for t in portal_tickets.list_tickets(
                'solutions',
                customer_user_id=self.users['solutions'],
                visibility='customer',
            )],
        )

    def test_cross_tenant_reads_and_filters_fail_closed(self):
        ticket = portal_tickets.create_ticket(
            'solutions',
            customer_user_id=self.users['solutions'],
            subject='Private',
        )
        self.assertIsNone(
            portal_tickets.get_ticket('adventures', ticket.id)
        )
        with self.assertRaises(ValueError):
            portal_tickets.list_tickets(
                'solutions',
                customer_user_id=self.users['adventures'],
            )

    def test_archived_ticket_hidden_and_immutable(self):
        ticket = portal_tickets.create_ticket(
            'solutions',
            customer_user_id=self.users['solutions'],
            subject='Old',
        )
        archived = portal_tickets.archive_ticket('solutions', ticket.id)
        self.assertEqual('archived', archived.status)
        self.assertEqual([], portal_tickets.list_tickets('solutions'))
        self.assertEqual(
            [ticket.id],
            [t.id for t in portal_tickets.list_tickets(
                'solutions', include_archived=True
            )],
        )
        with self.assertRaises(ValueError):
            portal_tickets.update_ticket(
                'solutions', ticket.id, subject='Blocked'
            )

    def test_validation(self):
        cases = (
            {'subject': ''},
            {'subject': 'Bad status', 'status': 'unknown'},
            {'subject': 'Bad priority', 'priority': 'critical'},
            {'subject': 'Bad visibility', 'visibility': 'public'},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    portal_tickets.create_ticket(
                        'solutions',
                        customer_user_id=self.users['solutions'],
                        **kwargs,
                    )

    def test_revoked_customer_membership_cannot_create_or_filter(self):
        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_memberships SET status='revoked' WHERE user_id=?",
                (self.users['solutions'],),
            )
            conn.commit()
        with self.assertRaises(ValueError):
            portal_tickets.create_ticket(
                'solutions',
                customer_user_id=self.users['solutions'],
                subject='Blocked',
            )
        with self.assertRaises(ValueError):
            portal_tickets.list_tickets(
                'solutions',
                customer_user_id=self.users['solutions'],
            )

    def _create_extra_customer(self, slug, email):
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
                    ts, ts, org['id'], email, 'Second', 'Customer',
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
