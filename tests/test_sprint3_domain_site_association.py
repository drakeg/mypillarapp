from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import tenant_auth
import tenant_context
import tenant_sites


class Sprint3DomainSiteAssociationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        tenant_auth.DATA_DIR = data_dir
        tenant_auth.DB_PATH = data_dir / 'madmallard.sqlite3'
        tenant_auth.PRIMARY_DOMAIN = 'pillar.madmallards.com'
        tenant_context.ensure_schema()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_seeded_primary_domain_is_attached_to_main_site(self):
        site = tenant_context.resolve_site('pillar.madmallards.com')

        self.assertIsNotNone(site)
        self.assertEqual('solutions', site.organization_slug)
        self.assertEqual('main', site.slug)

    def test_existing_tenant_resolution_contract_is_preserved(self):
        tenant = tenant_context.resolve_tenant('pillar.madmallards.com')

        self.assertIsNotNone(tenant)
        self.assertEqual('solutions', tenant.slug)
        self.assertEqual('pillar.madmallards.com', tenant.domain)

    def test_domain_can_target_non_main_site_in_same_organization(self):
        tenant_sites.create_site(
            'solutions',
            slug='campaign',
            name='Campaign',
            status='published',
        )

        self.assertTrue(
            tenant_context.register_domain(
                'solutions',
                'campaign.example.com',
                site_slug='campaign',
            )
        )

        site = tenant_context.resolve_site('campaign.example.com')
        self.assertEqual('solutions', site.organization_slug)
        self.assertEqual('campaign', site.slug)

    def test_same_domain_cannot_be_reassigned_across_organizations(self):
        self.assertTrue(
            tenant_context.register_domain(
                'solutions',
                'shared.example.com',
            )
        )

        self.assertFalse(
            tenant_context.register_domain(
                'personal-training',
                'SHARED.EXAMPLE.COM:443',
            )
        )

        tenant = tenant_context.resolve_tenant('shared.example.com')
        site = tenant_context.resolve_site('shared.example.com')
        self.assertEqual('solutions', tenant.slug)
        self.assertEqual('solutions', site.organization_slug)

    def test_domain_cannot_attach_to_site_owned_by_another_organization(self):
        tenant_sites.create_site(
            'solutions',
            slug='solutions-only',
            name='Solutions Only',
        )

        self.assertFalse(
            tenant_context.register_domain(
                'personal-training',
                'training.example.com',
                site_slug='solutions-only',
            )
        )
        self.assertIsNone(tenant_context.resolve_tenant('training.example.com'))

    def test_archived_site_cannot_receive_new_domain(self):
        tenant_sites.create_site(
            'solutions',
            slug='seasonal',
            name='Seasonal',
        )
        tenant_sites.archive_site('solutions', 'seasonal')

        self.assertFalse(
            tenant_context.register_domain(
                'solutions',
                'seasonal.example.com',
                site_slug='seasonal',
            )
        )

    def test_resolve_site_rejects_domain_when_attached_site_is_archived(self):
        tenant_sites.create_site(
            'solutions',
            slug='seasonal',
            name='Seasonal',
        )
        self.assertTrue(
            tenant_context.register_domain(
                'solutions',
                'seasonal.example.com',
                site_slug='seasonal',
            )
        )
        tenant_sites.archive_site('solutions', 'seasonal')

        self.assertIsNone(tenant_context.resolve_site('seasonal.example.com'))
        self.assertEqual(
            'solutions',
            tenant_context.resolve_tenant('seasonal.example.com').slug,
        )

    def test_legacy_domain_without_site_id_is_migrated_to_main_site(self):
        other_data = Path(self.temp_dir.name) / 'legacy'
        other_data.mkdir()
        tenant_auth.DATA_DIR = other_data
        tenant_auth.DB_PATH = other_data / 'madmallard.sqlite3'

        with tenant_auth.db() as conn:
            organization = conn.execute(
                "SELECT id FROM auth_organizations WHERE slug = 'personal-training'"
            ).fetchone()
            timestamp = tenant_auth.now()
            conn.execute(
                '''
                CREATE TABLE tenant_domains (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    organization_id INTEGER NOT NULL,
                    domain TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    is_primary INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                '''
            )
            conn.execute(
                '''
                INSERT INTO tenant_domains(
                    organization_id, domain, is_primary, is_active,
                    created_at, updated_at
                ) VALUES (?, ?, 1, 1, ?, ?)
                ''',
                (
                    organization['id'],
                    'legacy-training.example.com',
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()

        tenant_context.ensure_schema()

        site = tenant_context.resolve_site('legacy-training.example.com')
        self.assertIsNotNone(site)
        self.assertEqual('personal-training', site.organization_slug)
        self.assertEqual('main', site.slug)


if __name__ == '__main__':
    unittest.main()
