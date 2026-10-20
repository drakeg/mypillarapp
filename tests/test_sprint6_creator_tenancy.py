from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import creator_tenancy
import site_media
import site_navigation
import tenant_auth
import tenant_context
import tenant_memberships
import tenant_sites


class Sprint6CreatorBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_context.ensure_schema()
        self.user_id = self._user('solutions', 'creator@example.com')

    def tearDown(self):
        self.tmp.cleanup()

    def _user(self, slug, email):
        with tenant_auth.db() as conn:
            org = conn.execute(
                'SELECT id FROM auth_organizations WHERE slug=?', (slug,)
            ).fetchone()
            role = conn.execute(
                "SELECT id FROM auth_roles WHERE slug='staff'"
            ).fetchone()
            ts = tenant_auth.now()
            cur = conn.execute(
                """INSERT INTO auth_users(
                       created_at,updated_at,organization_id,email,
                       first_name,last_name,password_hash,role,is_active
                   ) VALUES(?,?,?,?,?,?,?,?,1)""",
                (
                    ts, ts, org['id'], email, 'Creator', 'User',
                    tenant_auth.hash_password('abcdefghijkl'), 'staff',
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

    def test_authoring_scope_requires_same_active_tenant_membership(self):
        scope = creator_tenancy.authoring_scope(
            self.user_id, 'solutions', 'main'
        )
        self.assertEqual('solutions', scope.organization_slug)
        self.assertEqual('main', scope.site_slug)

        with self.assertRaises(PermissionError):
            creator_tenancy.authoring_scope(
                self.user_id, 'adventures', 'main'
            )

    def test_revoked_membership_and_inactive_tenant_fail_closed(self):
        tenant_memberships.revoke_membership(
            self.user_id, 'solutions'
        )
        with self.assertRaises(PermissionError):
            creator_tenancy.authoring_scope(
                self.user_id, 'solutions', 'main'
            )

        tenant_memberships.grant_membership(
            self.user_id, 'solutions', 'staff'
        )
        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_organizations SET status='suspended' "
                "WHERE slug='solutions'"
            )
            conn.commit()
        with self.assertRaises(PermissionError):
            creator_tenancy.authoring_scope(
                self.user_id, 'solutions', 'main'
            )

    def test_archived_site_cannot_be_authored(self):
        tenant_sites.archive_site('solutions', 'main')
        with self.assertRaises(PermissionError):
            creator_tenancy.authoring_scope(
                self.user_id, 'solutions', 'main'
            )

    def test_public_scope_requires_active_domain_and_published_site(self):
        tenant_context.register_domain(
            'solutions', 'creator.example.com', site_slug='main'
        )
        self.assertIsNone(
            creator_tenancy.public_scope('creator.example.com')
        )
        tenant_sites.update_site(
            'solutions', 'main', status='published'
        )
        scope = creator_tenancy.public_scope('creator.example.com')
        self.assertIsNotNone(scope)
        self.assertEqual('solutions', scope.organization_slug)

        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE tenant_domains SET is_active=0 "
                "WHERE domain='creator.example.com'"
            )
            conn.commit()
        self.assertIsNone(
            creator_tenancy.public_scope('creator.example.com')
        )

    def test_audit_flags_http_and_credentialed_legacy_urls(self):
        site_navigation.create_item(
            'solutions', 'main',
            label='Legacy affiliate',
            target='http://example.com/product',
        )
        site_media.create_media(
            'solutions', 'main',
            slug='legacy-media',
            kind='image',
            source='https://user:secret@example.com/image.jpg',
        )
        audit = creator_tenancy.audit_existing_creator_content()
        self.assertEqual(1, audit.external_navigation_links)
        self.assertEqual(1, audit.external_media_sources)
        self.assertEqual(1, audit.insecure_http_urls)
        self.assertEqual(1, audit.credentialed_urls)
        self.assertFalse(audit.safe_for_creator_migration)

    def test_clean_https_content_is_safe_for_creator_migration(self):
        site_navigation.create_item(
            'solutions', 'main',
            label='Gear',
            target='https://example.com/gear',
        )
        site_media.create_media(
            'solutions', 'main',
            slug='hero',
            kind='image',
            source='https://example.com/hero.jpg',
        )
        audit = creator_tenancy.audit_existing_creator_content()
        self.assertEqual(0, audit.insecure_http_urls)
        self.assertEqual(0, audit.credentialed_urls)
        self.assertEqual(0, audit.domain_site_mismatches)
        self.assertTrue(audit.safe_for_creator_migration)


if __name__ == '__main__':
    unittest.main()
