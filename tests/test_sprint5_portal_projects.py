from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import crm_companies
import crm_contacts
import crm_opportunities
import portal_projects
import tenant_auth


class Sprint5ServiceProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        with tenant_auth.db() as conn:
            ts = tenant_auth.now()
            self.users = {}
            for slug, email in (
                ('solutions', 'customer@example.com'),
                ('adventures', 'traveler@example.com'),
            ):
                org = conn.execute(
                    'SELECT id FROM auth_organizations WHERE slug=?', (slug,)
                ).fetchone()
                role = conn.execute(
                    "SELECT id FROM auth_roles WHERE slug='viewer'"
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
                user_id = int(cur.lastrowid)
                conn.execute(
                    """INSERT INTO auth_memberships(
                           created_at,updated_at,user_id,organization_id,
                           role_id,status
                       ) VALUES(?,?,?,?,?,'active')""",
                    (ts, ts, user_id, org['id'], role['id']),
                )
                self.users[slug] = user_id
            conn.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def test_project_crud_customer_scope_and_dates(self):
        project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.users['solutions'],
            title='Cloud modernization',
            summary='Move workloads safely.',
            status='active',
            start_date='2026-10-15',
            due_date='2026-12-01',
        )
        self.assertEqual('customer@example.com', project.customer_email)
        self.assertEqual('active', project.status)
        updated = portal_projects.update_project(
            'solutions', project.id,
            status='on_hold', summary='Waiting on customer input.'
        )
        self.assertEqual('on_hold', updated.status)
        self.assertEqual(
            [project.id],
            [p.id for p in portal_projects.list_projects(
                'solutions', customer_user_id=self.users['solutions']
            )],
        )

    def test_foreign_customer_is_rejected(self):
        with self.assertRaises(ValueError):
            portal_projects.create_project(
                'solutions',
                customer_user_id=self.users['adventures'],
                title='Blocked',
            )

    def test_crm_links_must_be_same_tenant_and_consistent(self):
        company = crm_companies.create_company('solutions', name='Acme')
        contact = crm_contacts.create_contact(
            'solutions', name='Jane', company_id=company.id
        )
        opportunity = crm_opportunities.create_opportunity(
            'solutions', title='Deal',
            company_id=company.id, contact_id=contact.id
        )
        project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.users['solutions'],
            title='Linked',
            company_id=company.id,
            contact_id=contact.id,
            opportunity_id=opportunity.id,
        )
        self.assertEqual(company.id, project.company_id)
        foreign = crm_companies.create_company('adventures', name='Foreign')
        with self.assertRaises(ValueError):
            portal_projects.create_project(
                'solutions',
                customer_user_id=self.users['solutions'],
                title='Blocked',
                company_id=foreign.id,
            )

        second = crm_companies.create_company('solutions', name='Second')
        with self.assertRaisesRegex(ValueError, 'contact company'):
            portal_projects.create_project(
                'solutions',
                customer_user_id=self.users['solutions'],
                title='Mismatch',
                company_id=second.id,
                contact_id=contact.id,
            )

    def test_cross_tenant_project_reads_do_not_leak(self):
        project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.users['solutions'],
            title='Private',
        )
        self.assertIsNone(
            portal_projects.get_project('adventures', project.id)
        )
        self.assertEqual(
            [],
            portal_projects.list_projects(
                'adventures',
                customer_user_id=self.users['adventures'],
            ),
        )

    def test_archived_project_hidden_and_immutable(self):
        project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.users['solutions'],
            title='Old',
        )
        archived = portal_projects.archive_project('solutions', project.id)
        self.assertEqual('archived', archived.status)
        self.assertEqual([], portal_projects.list_projects('solutions'))
        self.assertEqual(
            [project.id],
            [p.id for p in portal_projects.list_projects(
                'solutions', include_archived=True
            )],
        )
        with self.assertRaises(ValueError):
            portal_projects.update_project(
                'solutions', project.id, title='Blocked'
            )

    def test_validation(self):
        with self.assertRaises(ValueError):
            portal_projects.create_project(
                'solutions',
                customer_user_id=self.users['solutions'],
                title='',
            )
        with self.assertRaises(ValueError):
            portal_projects.create_project(
                'solutions',
                customer_user_id=self.users['solutions'],
                title='Bad status',
                status='unknown',
            )
        with self.assertRaises(ValueError):
            portal_projects.create_project(
                'solutions',
                customer_user_id=self.users['solutions'],
                title='Bad date',
                start_date='10/15/2026',
            )
        with self.assertRaises(ValueError):
            portal_projects.create_project(
                'solutions',
                customer_user_id=self.users['solutions'],
                title='Bad order',
                start_date='2026-12-01',
                due_date='2026-11-01',
            )

    def test_revoked_customer_membership_cannot_be_used(self):
        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_memberships SET status='revoked' WHERE user_id=?",
                (self.users['solutions'],),
            )
            conn.commit()
        with self.assertRaises(ValueError):
            portal_projects.create_project(
                'solutions',
                customer_user_id=self.users['solutions'],
                title='Blocked',
            )

    def test_inactive_customer_or_tenant_cannot_be_used(self):
        with tenant_auth.db() as conn:
            conn.execute(
                'UPDATE auth_users SET is_active=0 WHERE id=?',
                (self.users['solutions'],),
            )
            conn.commit()
        with self.assertRaises(ValueError):
            portal_projects.create_project(
                'solutions',
                customer_user_id=self.users['solutions'],
                title='Blocked',
            )

        with tenant_auth.db() as conn:
            conn.execute(
                'UPDATE auth_users SET is_active=1 WHERE id=?',
                (self.users['solutions'],),
            )
            conn.execute(
                "UPDATE auth_organizations SET status='suspended' "
                "WHERE slug='solutions'"
            )
            conn.commit()
        with self.assertRaises(ValueError):
            portal_projects.list_projects('solutions')


if __name__ == '__main__':
    unittest.main()
