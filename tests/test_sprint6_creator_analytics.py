from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS=Path(__file__).resolve().parents[1]/'site'/'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0,str(SOLUTIONS))

import creator_affiliates
import creator_analytics
import creator_collections
import creator_downloads
import creator_profiles
import creator_storefront
import tenant_auth
import tenant_sites


class Sprint6CreatorAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        data=Path(self.tmp.name)
        tenant_auth.DATA_DIR=data
        tenant_auth.DB_PATH=data/'madmallard.sqlite3'
        tenant_sites.ensure_schema()

    def tearDown(self):
        self.tmp.cleanup()

    def test_page_view_has_no_target_and_metadata_is_bounded(self):
        event=creator_analytics.record_event(
            'solutions','main',
            event_type='creator_page_view',
            metadata={'path':'/creator'}
        )
        self.assertEqual('',event.target_type)
        self.assertIsNone(event.target_id)
        self.assertEqual('/creator',event.metadata['path'])
        with self.assertRaises(ValueError):
            creator_analytics.record_event(
                'solutions','main',
                event_type='creator_page_view',
                target_type='product',
                target_id=1
            )

    def test_targeted_events_require_same_site_records(self):
        link=creator_profiles.create_link(
            'solutions','main',label='Home',target='/',status='published'
        )
        affiliate=creator_affiliates.create_affiliate(
            'solutions','main',label='Gear',
            destination_url='https://example.com/gear',
            disclosure_text='Affiliate',status='published'
        )
        collection=creator_collections.create_collection(
            'solutions','main',slug='videos',title='Videos',status='published'
        )
        download=creator_downloads.create_download(
            'solutions','main',title='Guide',
            source_type='storage_key',
            source_ref='downloads/guide/file.pdf',
            status='published'
        )
        product=creator_storefront.create_product(
            'solutions','main',title='Service',
            product_type='service',status='published'
        )
        cases=(
            ('creator_link_click','creator_link',link.id),
            ('affiliate_click','affiliate',affiliate.id),
            ('collection_open','collection',collection.id),
            ('download_view','download',download.id),
            ('product_view','product',product.id),
        )
        for event_type,target_type,target_id in cases:
            with self.subTest(event_type=event_type):
                event=creator_analytics.record_event(
                    'solutions','main',
                    event_type=event_type,
                    target_type=target_type,
                    target_id=target_id,
                )
                self.assertEqual(target_id,event.target_id)

    def test_cross_site_target_probe_fails_closed(self):
        tenant_sites.create_site('solutions',slug='other',name='Other')
        product=creator_storefront.create_product(
            'solutions','other',title='Private',
            product_type='service'
        )
        with self.assertRaises(ValueError):
            creator_analytics.record_event(
                'solutions','main',
                event_type='product_view',
                target_type='product',
                target_id=product.id,
            )

    def test_cross_tenant_reads_are_isolated(self):
        creator_analytics.record_event(
            'solutions','main',
            event_type='creator_page_view'
        )
        self.assertEqual(
            [],
            creator_analytics.list_events(
                'personal-training','main'
            )
        )

    def test_metadata_rejects_scripts_non_strings_and_oversize(self):
        for metadata in (
            {'x':'<script>alert(1)</script>'},
            {'x':'javascript:alert(1)'},
            {'x':'a'*501},
            {'x':123},
        ):
            with self.subTest(metadata=metadata):
                with self.assertRaises(ValueError):
                    creator_analytics.record_event(
                        'solutions','main',
                        event_type='creator_page_view',
                        metadata=metadata,
                    )

    def test_reads_are_bounded_filtered_and_newest_first(self):
        for i in range(3):
            creator_analytics.record_event(
                'solutions','main',
                event_type='creator_page_view',
                metadata={'n':str(i)}
            )
        rows=creator_analytics.list_events(
            'solutions','main',limit=2
        )
        self.assertEqual(2,len(rows))
        self.assertGreater(rows[0].id,rows[1].id)
        with self.assertRaises(ValueError):
            creator_analytics.list_events(
                'solutions','main',limit=501
            )
        with self.assertRaises(ValueError):
            creator_analytics.list_events(
                'solutions','main',event_type='unknown'
            )

    def test_event_types_do_not_accept_mismatched_targets(self):
        product=creator_storefront.create_product(
            'solutions','main',title='Service',
            product_type='service'
        )
        with self.assertRaises(ValueError):
            creator_analytics.record_event(
                'solutions','main',
                event_type='affiliate_click',
                target_type='product',
                target_id=product.id,
            )

    def test_archived_site_cannot_accept_events(self):
        tenant_sites.create_site(
            'solutions',slug='seasonal',name='Seasonal'
        )
        tenant_sites.archive_site('solutions','seasonal')
        with self.assertRaises(ValueError):
            creator_analytics.record_event(
                'solutions','seasonal',
                event_type='creator_page_view'
            )

    def test_analytics_has_no_cross_site_identity_profile_fields(self):
        event=creator_analytics.record_event(
            'solutions','main',
            event_type='creator_page_view'
        )
        for field in (
            'email','user_id','customer_id','advertising_id',
            'ip_address','cross_site_id'
        ):
            self.assertFalse(hasattr(event,field))


if __name__=='__main__':
    unittest.main()
