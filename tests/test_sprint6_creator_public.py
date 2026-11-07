from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS=Path(__file__).resolve().parents[1]/'site'/'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0,str(SOLUTIONS))

import creator_affiliates
import creator_collections
import creator_downloads
import creator_profiles
import creator_storefront
import public_site_renderer
import tenant_auth
import tenant_context
import tenant_sites


class Sprint6CreatorPublicRenderingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        data=Path(self.tmp.name)
        tenant_auth.DATA_DIR=data
        tenant_auth.DB_PATH=data/'madmallard.sqlite3'
        tenant_context.ensure_schema()
        tenant_context.register_domain(
            'adventures','creator.example.com',site_slug='main'
        )
        tenant_sites.update_site('adventures','main',status='published')

    def tearDown(self):
        self.tmp.cleanup()

    def test_creator_page_renders_only_published_escaped_content(self):
        creator_profiles.upsert_profile(
            'adventures','main',
            display_name='<Mallards>',
            bio='<script>alert(1)</script>',
            status='published',
        )
        creator_profiles.create_link(
            'adventures','main',
            label='<YouTube>',
            target='https://example.com/channel',
            status='published',
        )
        creator_profiles.create_link(
            'adventures','main',
            label='Draft',
            target='https://example.com/draft',
            status='draft',
        )
        result=public_site_renderer.render_public_path(
            'creator.example.com','/creator'
        )
        self.assertEqual(200,result.status)
        self.assertIn('&lt;Mallards&gt;',result.body)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;',result.body)
        self.assertIn('&lt;YouTube&gt;',result.body)
        self.assertNotIn('>Draft<',result.body)

    def test_affiliate_disclosure_is_visible_and_published_only(self):
        creator_profiles.upsert_profile(
            'adventures','main',display_name='Creator',status='published'
        )
        creator_affiliates.create_affiliate(
            'adventures','main',
            label='Gear',
            destination_url='https://example.com/gear',
            disclosure_text='We may earn a commission.',
            status='published',
        )
        creator_affiliates.create_affiliate(
            'adventures','main',
            label='Hidden',
            destination_url='https://example.com/hidden',
            disclosure_text='Affiliate',
            status='draft',
        )
        result=public_site_renderer.render_public_path(
            'creator.example.com','/creator'
        )
        self.assertIn('Affiliate disclosure:',result.body)
        self.assertIn('We may earn a commission.',result.body)
        self.assertIn('rel="sponsored nofollow"',result.body)
        self.assertNotIn('Hidden',result.body)

    def test_collections_are_published_only_and_items_are_escaped(self):
        creator_profiles.upsert_profile(
            'adventures','main',display_name='Creator',status='published'
        )
        published=creator_collections.create_collection(
            'adventures','main',slug='videos',title='Videos',
            description='<best>',status='published'
        )
        creator_collections.create_item(
            'adventures','main',published.id,
            title='<Episode>',target='/pages/trip'
        )
        creator_collections.create_collection(
            'adventures','main',slug='draft',title='Draft',
            status='draft'
        )
        result=public_site_renderer.render_public_path(
            'creator.example.com','/creator'
        )
        self.assertIn('&lt;best&gt;',result.body)
        self.assertIn('&lt;Episode&gt;',result.body)
        self.assertNotIn('>Draft<',result.body)

    def test_storefront_never_exposes_storage_keys(self):
        download=creator_downloads.create_download(
            'adventures','main',
            title='Guide',
            source_type='storage_key',
            source_ref='downloads/private/guide.pdf',
            visibility='public',
            status='published',
        )
        creator_storefront.create_product(
            'adventures','main',
            title='Guide',
            product_type='digital_download',
            download_id=download.id,
            price_cents=0,
            status='published',
        )
        result=public_site_renderer.render_public_path(
            'creator.example.com','/store'
        )
        self.assertEqual(200,result.status)
        self.assertIn('Guide',result.body)
        self.assertIn('USD 0.00',result.body)
        self.assertIn('managed platform',result.body)
        self.assertNotIn('downloads/private/guide.pdf',result.body)

    def test_external_download_and_external_product_urls_are_safe_outputs(self):
        download=creator_downloads.create_download(
            'adventures','main',
            title='Checklist',
            source_type='external_url',
            source_ref='https://example.com/checklist.pdf',
            visibility='public',
            status='published',
        )
        creator_storefront.create_product(
            'adventures','main',
            title='Checklist',
            product_type='digital_download',
            download_id=download.id,
            status='published',
        )
        creator_storefront.create_product(
            'adventures','main',
            title='External merch',
            product_type='external',
            external_url='https://example.com/merch',
            status='published',
        )
        result=public_site_renderer.render_public_path(
            'creator.example.com','/store'
        )
        self.assertIn('https://example.com/checklist.pdf',result.body)
        self.assertIn('https://example.com/merch',result.body)
        self.assertIn('rel="nofollow"',result.body)

    def test_unpublished_site_or_profile_is_not_public(self):
        creator_profiles.upsert_profile(
            'adventures','main',display_name='Draft Creator',status='draft'
        )
        result=public_site_renderer.render_public_path(
            'creator.example.com','/creator'
        )
        self.assertEqual(404,result.status)
        tenant_sites.update_site('adventures','main',status='draft')
        result=public_site_renderer.render_public_path(
            'creator.example.com','/store'
        )
        self.assertEqual(404,result.status)

    def test_solutions_static_compatibility_fallback_is_preserved(self):
        result=public_site_renderer.render_public_path(
            tenant_auth.PRIMARY_DOMAIN,'/creator'
        )
        self.assertIsNone(result)


if __name__=='__main__':
    unittest.main()
