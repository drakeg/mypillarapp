from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import portal_files
import portal_projects
import portal_tickets
import tenant_auth


class Sprint5PortalFileTests(unittest.TestCase):
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

    def test_file_metadata_links_to_same_customer_project_and_ticket(self):
        project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.users['solutions'],
            title='Portal project',
        )
        ticket = portal_tickets.create_ticket(
            'solutions',
            customer_user_id=self.users['solutions'],
            project_id=project.id,
            subject='Upload document',
        )
        file = portal_files.create_file(
            'solutions',
            customer_user_id=self.users['solutions'],
            project_id=project.id,
            ticket_id=ticket.id,
            name='statement.pdf',
            source_type='storage_key',
            source_ref='tenant/solutions/files/statement-1',
            mime_type='application/pdf',
        )
        self.assertEqual(project.id, file.project_id)
        self.assertEqual(ticket.id, file.ticket_id)
        self.assertEqual('customer', file.visibility)

    def test_foreign_customer_project_and_ticket_fail_closed(self):
        foreign_project = portal_projects.create_project(
            'adventures',
            customer_user_id=self.users['adventures'],
            title='Foreign',
        )
        foreign_ticket = portal_tickets.create_ticket(
            'adventures',
            customer_user_id=self.users['adventures'],
            project_id=foreign_project.id,
            subject='Foreign',
        )
        with self.assertRaises(ValueError):
            portal_files.create_file(
                'solutions',
                customer_user_id=self.users['solutions'],
                project_id=foreign_project.id,
                name='blocked.pdf',
                source_type='storage_key',
                source_ref='safe/key',
            )
        with self.assertRaises(ValueError):
            portal_files.create_file(
                'solutions',
                customer_user_id=self.users['solutions'],
                ticket_id=foreign_ticket.id,
                name='blocked.pdf',
                source_type='storage_key',
                source_ref='safe/key',
            )

    def test_project_ticket_relationship_must_be_consistent(self):
        first = portal_projects.create_project(
            'solutions',
            customer_user_id=self.users['solutions'],
            title='First',
        )
        second = portal_projects.create_project(
            'solutions',
            customer_user_id=self.users['solutions'],
            title='Second',
        )
        ticket = portal_tickets.create_ticket(
            'solutions',
            customer_user_id=self.users['solutions'],
            project_id=first.id,
            subject='First ticket',
        )
        with self.assertRaisesRegex(ValueError, 'ticket project'):
            portal_files.create_file(
                'solutions',
                customer_user_id=self.users['solutions'],
                project_id=second.id,
                ticket_id=ticket.id,
                name='blocked.txt',
                source_type='storage_key',
                source_ref='safe/key',
            )

    def test_source_validation_rejects_local_paths_and_unsafe_urls(self):
        cases = (
            ('storage_key', '/etc/passwd'),
            ('storage_key', '../secret'),
            ('storage_key', 'tenant//secret'),
            ('storage_key', 'file:///tmp/a'),
            ('external_url', 'http://example.com/file.pdf'),
            ('external_url', 'https://user:pass@example.com/file.pdf'),
        )
        for source_type, source_ref in cases:
            with self.subTest(source_type=source_type, source_ref=source_ref):
                with self.assertRaises(ValueError):
                    portal_files.create_file(
                        'solutions',
                        customer_user_id=self.users['solutions'],
                        name='blocked.pdf',
                        source_type=source_type,
                        source_ref=source_ref,
                    )

    def test_https_url_and_visibility_filters(self):
        visible = portal_files.create_file(
            'solutions',
            customer_user_id=self.users['solutions'],
            name='guide.pdf',
            source_type='external_url',
            source_ref='https://files.example.com/guide.pdf',
            visibility='customer',
        )
        portal_files.create_file(
            'solutions',
            customer_user_id=self.users['solutions'],
            name='internal.txt',
            source_type='storage_key',
            source_ref='tenant/solutions/internal/note',
            visibility='internal',
        )
        self.assertEqual(
            [visible.id],
            [f.id for f in portal_files.list_files(
                'solutions',
                customer_user_id=self.users['solutions'],
                visibility='customer',
            )],
        )

    def test_cross_tenant_reads_are_isolated(self):
        file = portal_files.create_file(
            'solutions',
            customer_user_id=self.users['solutions'],
            name='private.pdf',
            source_type='storage_key',
            source_ref='tenant/solutions/private/doc',
        )
        self.assertIsNone(portal_files.get_file('adventures', file.id))

    def test_customer_filter_rejects_foreign_customer(self):
        with self.assertRaises(ValueError):
            portal_files.list_files(
                'solutions',
                customer_user_id=self.users['adventures'],
            )

    def test_visibility_can_be_changed_without_changing_source(self):
        file = portal_files.create_file(
            'solutions',
            customer_user_id=self.users['solutions'],
            name='draft.pdf',
            source_type='storage_key',
            source_ref='tenant/solutions/draft/doc',
        )
        updated = portal_files.update_visibility(
            'solutions', file.id, 'internal'
        )
        self.assertEqual('internal', updated.visibility)
        self.assertEqual(file.source_ref, updated.source_ref)

    def test_validation(self):
        for kwargs in (
            {'name':'', 'source_type':'storage_key', 'source_ref':'safe/key'},
            {'name':'folder/file', 'source_type':'storage_key', 'source_ref':'safe/key'},
            {'name':'file', 'source_type':'unknown', 'source_ref':'safe/key'},
            {'name':'file', 'source_type':'storage_key', 'source_ref':''},
            {'name':'file', 'source_type':'storage_key', 'source_ref':'safe/key', 'visibility':'public'},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    portal_files.create_file(
                        'solutions',
                        customer_user_id=self.users['solutions'],
                        **kwargs,
                    )


if __name__ == '__main__':
    unittest.main()
