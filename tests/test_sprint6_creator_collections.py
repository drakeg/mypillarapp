from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import creator_collections
import tenant_auth
import tenant_sites


class Sprint6CreatorCollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

    def tearDown(self):
        self.tmp.cleanup()

    def test_collection_slug_is_unique_per_site(self):
        first = creator_collections.create_collection(
            'solutions','main',slug='gear',title='Gear'
        )
        self.assertEqual('gear', first.slug)
        with self.assertRaises(ValueError):
            creator_collections.create_collection(
                'solutions','main',slug='gear',title='Duplicate'
            )
        tenant_sites.create_site('solutions',slug='creator',name='Creator')
        other = creator_collections.create_collection(
            'solutions','creator',slug='gear',title='Other Gear'
        )
        self.assertEqual('gear', other.slug)

    def test_collection_validation_and_published_filter(self):
        with self.assertRaises(ValueError):
            creator_collections.create_collection(
                'solutions','main',slug='Bad Slug',title='Bad'
            )
        with self.assertRaises(ValueError):
            creator_collections.create_collection(
                'solutions','main',slug='empty',title=' '
            )
        published = creator_collections.create_collection(
            'solutions','main',slug='travel',title='Travel',
            position=10,status='published'
        )
        creator_collections.create_collection(
            'solutions','main',slug='draft',title='Draft',status='draft'
        )
        rows=creator_collections.list_collections(
            'solutions','main',published_only=True
        )
        self.assertEqual([published.id],[row.id for row in rows])

    def test_items_accept_safe_internal_and_https_targets(self):
        collection=creator_collections.create_collection(
            'solutions','main',slug='videos',title='Videos'
        )
        internal=creator_collections.create_item(
            'solutions','main',collection.id,
            title='Local',target='/videos/local'
        )
        external=creator_collections.create_item(
            'solutions','main',collection.id,
            title='YouTube',target='https://example.com/video'
        )
        self.assertEqual('/videos/local', internal.target)
        self.assertEqual('https://example.com/video', external.target)

    def test_unsafe_item_targets_are_rejected(self):
        collection=creator_collections.create_collection(
            'solutions','main',slug='unsafe',title='Unsafe'
        )
        for target in (
            '', '//evil.example.com', 'http://example.com',
            'https://user:secret@example.com/x',
            'javascript:alert(1)', 'ftp://example.com/file',
        ):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    creator_collections.create_item(
                        'solutions','main',collection.id,
                        title='Unsafe',target=target
                    )

    def test_collection_and_items_are_deterministically_ordered(self):
        third=creator_collections.create_collection(
            'solutions','main',slug='third',title='Third',
            position=20,status='published'
        )
        first=creator_collections.create_collection(
            'solutions','main',slug='first',title='First',
            position=10,status='published'
        )
        second=creator_collections.create_collection(
            'solutions','main',slug='second',title='Second',
            position=10,status='published'
        )
        rows=creator_collections.list_collections('solutions','main')
        self.assertEqual(
            [first.id,second.id,third.id],
            [row.id for row in rows]
        )

        collection=first
        i3=creator_collections.create_item(
            'solutions','main',collection.id,
            title='Third',target='/3',position=20
        )
        i1=creator_collections.create_item(
            'solutions','main',collection.id,
            title='First',target='/1',position=10
        )
        i2=creator_collections.create_item(
            'solutions','main',collection.id,
            title='Second',target='/2',position=10
        )
        items=creator_collections.list_items(
            'solutions','main',collection.id
        )
        self.assertEqual([i1.id,i2.id,i3.id],[row.id for row in items])

    def test_cross_site_and_cross_tenant_access_fail_closed(self):
        tenant_sites.create_site('solutions',slug='creator',name='Creator')
        collection=creator_collections.create_collection(
            'solutions','creator',slug='private',title='Private'
        )
        item=creator_collections.create_item(
            'solutions','creator',collection.id,
            title='Private item',target='/private'
        )
        self.assertIsNone(
            creator_collections.get_collection(
                'solutions','main',collection.id
            )
        )
        self.assertEqual(
            [],
            creator_collections.list_items(
                'personal-training','main',collection.id
            )
        )
        self.assertIsNone(
            creator_collections.update_item(
                'personal-training','main',
                collection.id,item.id,title='Wrong tenant'
            )
        )

    def test_archived_collection_is_immutable_and_items_cannot_change(self):
        collection=creator_collections.create_collection(
            'solutions','main',slug='archive',title='Archive'
        )
        item=creator_collections.create_item(
            'solutions','main',collection.id,
            title='Before',target='/before'
        )
        archived=creator_collections.archive_collection(
            'solutions','main',collection.id
        )
        self.assertEqual('archived', archived.status)
        self.assertEqual(
            [],
            creator_collections.list_collections(
                'solutions','main'
            )
        )
        with self.assertRaises(ValueError):
            creator_collections.update_collection(
                'solutions','main',collection.id,title='Nope'
            )
        with self.assertRaises(ValueError):
            creator_collections.update_item(
                'solutions','main',collection.id,item.id,title='Nope'
            )
        with self.assertRaises(ValueError):
            creator_collections.create_item(
                'solutions','main',collection.id,
                title='Nope',target='/nope'
            )

    def test_archived_site_cannot_be_modified(self):
        tenant_sites.create_site(
            'solutions',slug='seasonal',name='Seasonal'
        )
        collection=creator_collections.create_collection(
            'solutions','seasonal',slug='before',title='Before'
        )
        tenant_sites.archive_site('solutions','seasonal')
        with self.assertRaises(ValueError):
            creator_collections.create_collection(
                'solutions','seasonal',slug='nope',title='Nope'
            )
        with self.assertRaises(ValueError):
            creator_collections.create_item(
                'solutions','seasonal',collection.id,
                title='Nope',target='/nope'
            )


if __name__ == '__main__':
    unittest.main()
