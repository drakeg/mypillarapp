from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import site_navigation
import tenant_auth
import tenant_sites


class Sprint3NavigationModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        tenant_auth.DATA_DIR = data_dir
        tenant_auth.DB_PATH = data_dir / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_items_are_ordered_by_position_then_id(self):
        site_navigation.create_item(
            'solutions', 'main', label='Contact', target='/contact', position=20
        )
        first = site_navigation.create_item(
            'solutions', 'main', label='Home', target='/', position=10
        )
        second = site_navigation.create_item(
            'solutions', 'main', label='Services', target='/services', position=10
        )

        items = site_navigation.list_items('solutions', 'main')

        self.assertEqual([first.id, second.id], [items[0].id, items[1].id])
        self.assertEqual('Contact', items[2].label)

    def test_internal_and_https_external_targets_are_allowed(self):
        internal = site_navigation.create_item(
            'solutions', 'main', label='About', target='/about'
        )
        external = site_navigation.create_item(
            'solutions',
            'main',
            label='Docs',
            target='https://example.com/docs',
        )

        self.assertEqual('/about', internal.target)
        self.assertEqual('https://example.com/docs', external.target)

    def test_unsafe_targets_are_rejected(self):
        for target in (
            'javascript:alert(1)',
            '//evil.example.com',
            'ftp://example.com/file',
            '',
        ):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    site_navigation.create_item(
                        'solutions',
                        'main',
                        label='Unsafe',
                        target=target,
                    )

    def test_visibility_filter_hides_disabled_items(self):
        site_navigation.create_item(
            'solutions', 'main', label='Visible', target='/', is_visible=True
        )
        site_navigation.create_item(
            'solutions',
            'main',
            label='Hidden',
            target='/hidden',
            is_visible=False,
        )

        visible = site_navigation.list_items(
            'solutions', 'main', visible_only=True
        )

        self.assertEqual(['Visible'], [item.label for item in visible])

    def test_navigation_is_isolated_between_sites_in_same_tenant(self):
        tenant_sites.create_site('solutions', slug='campaign', name='Campaign')
        site_navigation.create_item(
            'solutions', 'main', label='Main', target='/'
        )
        site_navigation.create_item(
            'solutions',
            'campaign',
            label='Campaign',
            target='/campaign',
        )

        self.assertEqual(
            ['Main'],
            [item.label for item in site_navigation.list_items('solutions', 'main')],
        )
        self.assertEqual(
            ['Campaign'],
            [
                item.label
                for item in site_navigation.list_items(
                    'solutions', 'campaign'
                )
            ],
        )

    def test_same_site_slug_in_different_tenants_is_isolated(self):
        tenant_sites.create_site('solutions', slug='campaign', name='Solutions')
        tenant_sites.create_site(
            'personal-training',
            slug='campaign',
            name='Training',
        )
        site_navigation.create_item(
            'solutions', 'campaign', label='Solutions', target='/solutions'
        )

        self.assertEqual(
            [],
            site_navigation.list_items('personal-training', 'campaign'),
        )

    def test_cross_tenant_get_update_and_delete_fail(self):
        item = site_navigation.create_item(
            'solutions', 'main', label='Private', target='/private'
        )

        self.assertIsNone(
            site_navigation.get_item('personal-training', 'main', item.id)
        )
        self.assertIsNone(
            site_navigation.update_item(
                'personal-training',
                'main',
                item.id,
                label='Wrong Tenant',
            )
        )
        self.assertFalse(
            site_navigation.delete_item(
                'personal-training', 'main', item.id
            )
        )
        self.assertEqual(
            'Private',
            site_navigation.get_item('solutions', 'main', item.id).label,
        )

    def test_update_can_reorder_and_toggle_visibility(self):
        item = site_navigation.create_item(
            'solutions',
            'main',
            label='Old',
            target='/old',
            position=5,
        )

        updated = site_navigation.update_item(
            'solutions',
            'main',
            item.id,
            label='New',
            target='/new',
            position=50,
            is_visible=False,
        )

        self.assertEqual('New', updated.label)
        self.assertEqual('/new', updated.target)
        self.assertEqual(50, updated.position)
        self.assertFalse(updated.is_visible)

    def test_archived_site_cannot_be_modified(self):
        tenant_sites.create_site('solutions', slug='seasonal', name='Seasonal')
        item = site_navigation.create_item(
            'solutions',
            'seasonal',
            label='Before Archive',
            target='/seasonal',
        )
        tenant_sites.archive_site('solutions', 'seasonal')

        with self.assertRaises(ValueError):
            site_navigation.create_item(
                'solutions',
                'seasonal',
                label='Nope',
                target='/nope',
            )
        with self.assertRaises(ValueError):
            site_navigation.update_item(
                'solutions',
                'seasonal',
                item.id,
                label='Nope',
            )
        with self.assertRaises(ValueError):
            site_navigation.delete_item(
                'solutions',
                'seasonal',
                item.id,
            )

    def test_invalid_label_and_position_are_rejected(self):
        with self.assertRaises(ValueError):
            site_navigation.create_item(
                'solutions', 'main', label=' ', target='/'
            )
        with self.assertRaises(ValueError):
            site_navigation.create_item(
                'solutions',
                'main',
                label='Bad position',
                target='/',
                position=-1,
            )


if __name__ == '__main__':
    unittest.main()
