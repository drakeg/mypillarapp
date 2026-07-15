from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS_DIR = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
sys.path.insert(0, str(SOLUTIONS_DIR))

import messaging  # noqa: E402
import tenant_auth  # noqa: E402
import tenant_context  # noqa: E402


class Sprint2TenantFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        database = data_dir / 'madmallard.sqlite3'

        tenant_auth.DATA_DIR = data_dir
        tenant_auth.DB_PATH = database
        tenant_auth.PRIMARY_DOMAIN = 'pillar.madmallards.com'
        messaging.DATA_DIR = data_dir
        messaging.DB_PATH = database

        with tenant_auth.db():
            pass
        tenant_context.ensure_schema()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_primary_domain_resolves_to_solutions_tenant(self) -> None:
        tenant = tenant_context.resolve_tenant('pillar.madmallards.com')

        self.assertIsNotNone(tenant)
        self.assertEqual('solutions', tenant.slug)
        self.assertEqual('Mad Mallard Solutions', tenant.name)
        self.assertEqual('pillar.madmallards.com', tenant.domain)

    def test_host_normalization_handles_scheme_case_port_and_dot(self) -> None:
        self.assertEqual(
            'pillar.madmallards.com',
            tenant_context.normalize_host(
                'HTTPS://PILLAR.MADMALLARDS.COM:443/path'
            ),
        )
        self.assertEqual(
            'pillar.madmallards.com',
            tenant_context.normalize_host('PILLAR.MADMALLARDS.COM.'),
        )

    def test_unknown_domain_does_not_fall_back_to_another_tenant(self) -> None:
        self.assertIsNone(tenant_context.resolve_tenant('unknown.example.com'))

    def test_domains_are_isolated_between_tenants(self) -> None:
        self.assertTrue(
            tenant_context.register_domain(
                'personal-training',
                'training.madmallards.com',
                primary=True,
            )
        )
        self.assertTrue(
            tenant_context.register_domain(
                'adventures',
                'adventures.madmallards.com',
                primary=True,
            )
        )

        training = tenant_context.resolve_tenant('training.madmallards.com')
        adventures = tenant_context.resolve_tenant('adventures.madmallards.com')

        self.assertEqual('personal-training', training.slug)
        self.assertEqual('adventures', adventures.slug)
        self.assertNotEqual(training.id, adventures.id)

    def test_settings_are_scoped_to_one_tenant(self) -> None:
        self.assertTrue(
            tenant_context.set_setting(
                'solutions', 'support_email', 'support@example.com'
            )
        )
        self.assertTrue(
            tenant_context.set_setting(
                'personal-training', 'support_email', 'coach@example.com'
            )
        )
        self.assertTrue(
            tenant_context.set_setting(
                'solutions', 'features', {'chat': True, 'billing': False}
            )
        )

        solutions = tenant_context.get_settings('solutions')
        training = tenant_context.get_settings('personal-training')

        self.assertEqual('support@example.com', solutions['support_email'])
        self.assertEqual('coach@example.com', training['support_email'])
        self.assertEqual(
            {'chat': True, 'billing': False}, solutions['features']
        )
        self.assertNotIn('features', training)

    def test_tenant_lookup_by_slug_returns_primary_domain(self) -> None:
        tenant = tenant_context.get_tenant_by_slug('solutions')

        self.assertIsNotNone(tenant)
        self.assertEqual('pillar.madmallards.com', tenant.domain)


if __name__ == '__main__':
    unittest.main()
