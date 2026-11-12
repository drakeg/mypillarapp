from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import ai_boundary
import creator_profiles
import crm_companies
import portal_projects
import site_pages
import tenant_auth
import tenant_memberships
import tenant_sites


class Sprint7AIBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

        self.staff = self._user('solutions', 'staff@example.com', 'staff')
        self.viewer = self._user('solutions', 'viewer@example.com', 'viewer')
        self.customer = self._user('solutions', 'customer@example.com', 'viewer')
        self.other_staff = self._user(
            'personal-training', 'other-staff@example.com', 'staff'
        )
        self.other_customer = self._user(
            'personal-training', 'other-customer@example.com', 'viewer'
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _user(self, organization_slug, email, role):
        with tenant_auth.db() as conn:
            org = conn.execute(
                'SELECT id FROM auth_organizations WHERE slug=?',
                (organization_slug,),
            ).fetchone()
            role_row = conn.execute(
                'SELECT id FROM auth_roles WHERE slug=?',
                (role,),
            ).fetchone()
            now = tenant_auth.now()
            cur = conn.execute(
                '''INSERT INTO auth_users(
                       created_at,updated_at,organization_id,email,
                       first_name,last_name,password_hash,role,is_active
                   ) VALUES(?,?,?,?,?,?,?,?,1)''',
                (
                    now,
                    now,
                    org['id'],
                    email,
                    'AI',
                    'Tester',
                    tenant_auth.hash_password('abcdefghijkl'),
                    role,
                ),
            )
            user_id = int(cur.lastrowid)
            conn.execute(
                '''INSERT INTO auth_memberships(
                       created_at,updated_at,user_id,organization_id,
                       role_id,status
                   ) VALUES(?,?,?,?,?,'active')''',
                (now, now, user_id, org['id'], role_row['id']),
            )
            conn.commit()
        return user_id

    def test_active_membership_authorizes_tenant_and_site_scope(self):
        scope = ai_boundary.authorize_request(
            self.staff, 'solutions', site_slug='main'
        )
        self.assertEqual('solutions', scope.organization_slug)
        self.assertEqual('staff', scope.role)
        self.assertEqual('main', scope.site_slug)
        self.assertIsNotNone(scope.site_id)

    def test_revoked_disabled_and_suspended_access_fail_closed(self):
        tenant_memberships.revoke_membership(self.staff, 'solutions')
        with self.assertRaises(PermissionError):
            ai_boundary.authorize_request(self.staff, 'solutions')

        with tenant_auth.db() as conn:
            conn.execute(
                'UPDATE auth_users SET is_active=0 WHERE id=?',
                (self.viewer,),
            )
            conn.commit()
        with self.assertRaises(PermissionError):
            ai_boundary.authorize_request(self.viewer, 'solutions')

        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_organizations SET status='suspended' "
                "WHERE slug='personal-training'"
            )
            conn.commit()
        with self.assertRaises(PermissionError):
            ai_boundary.authorize_request(
                self.other_staff, 'personal-training'
            )

    def test_membership_is_explicit_and_cross_tenant_access_is_not_inferred(self):
        with self.assertRaises(PermissionError):
            ai_boundary.authorize_request(self.staff, 'personal-training')

        ok, _, membership = tenant_memberships.grant_membership(
            self.staff, 'personal-training', 'staff'
        )
        self.assertTrue(ok)
        self.assertIsNotNone(membership)
        scope = ai_boundary.authorize_request(
            self.staff, 'personal-training'
        )
        self.assertEqual('personal-training', scope.organization_slug)

    def test_platform_or_unknown_identity_has_no_implicit_ai_access(self):
        with self.assertRaises(PermissionError):
            ai_boundary.authorize_request(999999, 'solutions')

    def test_archived_site_fails_closed(self):
        tenant_sites.create_site(
            'solutions', slug='archive-me', name='Archive Me'
        )
        tenant_sites.archive_site('solutions', 'archive-me')
        with self.assertRaises(PermissionError):
            ai_boundary.authorize_request(
                self.staff, 'solutions', site_slug='archive-me'
            )

    def test_context_classification_allow_lists_and_blocks_sensitive_classes(self):
        self.assertEqual(
            'eligible', ai_boundary.classify_context('crm_company')
        )
        for context_class in (
            'auth_material',
            'provider_secret',
            'storage_key',
            'infrastructure_state',
            'portal_internal',
            'session_token',
        ):
            self.assertEqual(
                'blocked',
                ai_boundary.classify_context(context_class),
            )
        self.assertEqual(
            'unknown', ai_boundary.classify_context('arbitrary_blob')
        )
        self.assertEqual(
            'untrusted_generated_text',
            ai_boundary.OUTPUT_CLASSIFICATION,
        )

    def test_same_tenant_records_are_eligible_but_foreign_ids_fail_closed(self):
        own_company = crm_companies.create_company(
            'solutions', name='Solutions Customer'
        )
        foreign_company = crm_companies.create_company(
            'personal-training', name='PT Customer'
        )
        own_project = portal_projects.create_project(
            'solutions',
            customer_user_id=self.customer,
            title='Solutions Project',
        )
        foreign_project = portal_projects.create_project(
            'personal-training',
            customer_user_id=self.other_customer,
            title='PT Project',
        )
        scope = ai_boundary.authorize_request(self.staff, 'solutions')

        ai_boundary.validate_context_reference(
            scope,
            ai_boundary.AIContextReference(
                'crm_company', str(own_company.id)
            ),
        )
        ai_boundary.validate_context_reference(
            scope,
            ai_boundary.AIContextReference(
                'portal_project', str(own_project.id)
            ),
        )

        with self.assertRaises(PermissionError):
            ai_boundary.validate_context_reference(
                scope,
                ai_boundary.AIContextReference(
                    'crm_company', str(foreign_company.id)
                ),
            )
        with self.assertRaises(PermissionError):
            ai_boundary.validate_context_reference(
                scope,
                ai_boundary.AIContextReference(
                    'portal_project', str(foreign_project.id)
                ),
            )

    def test_site_scoped_context_cannot_cross_sites(self):
        site_pages.create_page(
            'solutions',
            'main',
            slug='home-ai',
            title='Main AI Page',
        )
        creator_profiles.upsert_profile(
            'solutions',
            'main',
            display_name='Main Creator',
        )
        link = creator_profiles.create_link(
            'solutions',
            'main',
            label='Home',
            target='/',
        )
        tenant_sites.create_site(
            'solutions', slug='second', name='Second Site'
        )
        site_pages.create_page(
            'solutions',
            'second',
            slug='second-ai',
            title='Second AI Page',
        )
        scope = ai_boundary.authorize_request(
            self.staff, 'solutions', site_slug='main'
        )

        checked = ai_boundary.validate_context_set(
            scope,
            (
                ai_boundary.AIContextReference(
                    'site_page', 'home-ai', site_slug='main'
                ),
                ai_boundary.AIContextReference(
                    'creator_profile', 'profile', site_slug='main'
                ),
                ai_boundary.AIContextReference(
                    'creator_link', str(link.id), site_slug='main'
                ),
            ),
        )
        self.assertEqual(3, len(checked))

        with self.assertRaises(PermissionError):
            ai_boundary.validate_context_reference(
                scope,
                ai_boundary.AIContextReference(
                    'site_page', 'second-ai', site_slug='second'
                ),
            )

    def test_sensitive_or_unknown_context_is_rejected_before_record_lookup(self):
        scope = ai_boundary.authorize_request(self.staff, 'solutions')
        for context_class in ('storage_key', 'provider_secret', 'mystery'):
            with self.assertRaises(PermissionError):
                ai_boundary.validate_context_reference(
                    scope,
                    ai_boundary.AIContextReference(
                        context_class, 'anything'
                    ),
                )


if __name__ == '__main__':
    unittest.main()
