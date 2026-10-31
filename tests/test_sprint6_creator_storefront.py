from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS=Path(__file__).resolve().parents[1]/'site'/'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0,str(SOLUTIONS))

import creator_downloads
import creator_storefront
import tenant_auth
import tenant_sites


class Sprint6StorefrontProductTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        data=Path(self.tmp.name)
        tenant_auth.DATA_DIR=data
        tenant_auth.DB_PATH=data/'madmallard.sqlite3'
        tenant_sites.ensure_schema()

    def tearDown(self):
        self.tmp.cleanup()

    def test_free_and_priced_catalog_metadata(self):
        free=creator_storefront.create_product(
            'solutions','main',title='Free guide',
            product_type='service',price_cents=0,currency='usd'
        )
        priced=creator_storefront.create_product(
            'solutions','main',title='Consultation',
            product_type='service',price_cents=12500,currency='USD'
        )
        self.assertEqual(0,free.price_cents)
        self.assertEqual(12500,priced.price_cents)
        self.assertEqual('USD',priced.currency)

    def test_price_and_currency_validation(self):
        for price in (-1,True,'abc'):
            with self.subTest(price=price):
                with self.assertRaises(ValueError):
                    creator_storefront.create_product(
                        'solutions','main',title='Bad',
                        product_type='service',price_cents=price
                    )
        with self.assertRaises(ValueError):
            creator_storefront.create_product(
                'solutions','main',title='Bad currency',
                product_type='service',currency='US'
            )

    def test_digital_product_requires_same_site_download(self):
        download=creator_downloads.create_download(
            'solutions','main',title='Guide',
            source_type='storage_key',
            source_ref='downloads/guide/file.pdf',
            status='published'
        )
        product=creator_storefront.create_product(
            'solutions','main',title='Guide product',
            product_type='digital_download',download_id=download.id
        )
        self.assertEqual(download.id,product.download_id)

        tenant_sites.create_site('solutions',slug='other',name='Other')
        other=creator_downloads.create_download(
            'solutions','other',title='Other',
            source_type='storage_key',
            source_ref='downloads/other/file.pdf'
        )
        with self.assertRaises(ValueError):
            creator_storefront.create_product(
                'solutions','main',title='Wrong site',
                product_type='digital_download',download_id=other.id
            )

    def test_type_relationships_are_explicit(self):
        with self.assertRaises(ValueError):
            creator_storefront.create_product(
                'solutions','main',title='Missing download',
                product_type='digital_download'
            )
        with self.assertRaises(ValueError):
            creator_storefront.create_product(
                'solutions','main',title='Missing external URL',
                product_type='external'
            )
        with self.assertRaises(ValueError):
            creator_storefront.create_product(
                'solutions','main',title='Wrong URL type',
                product_type='service',
                external_url='https://example.com'
            )
        external=creator_storefront.create_product(
            'solutions','main',title='External',
            product_type='external',
            external_url='https://example.com/product'
        )
        self.assertEqual('https://example.com/product',external.external_url)

    def test_storefront_ordering_and_published_filter(self):
        third=creator_storefront.create_product(
            'solutions','main',title='Third',
            product_type='service',position=20,status='published'
        )
        first=creator_storefront.create_product(
            'solutions','main',title='First',
            product_type='service',position=10,status='published'
        )
        second=creator_storefront.create_product(
            'solutions','main',title='Second',
            product_type='service',position=10,status='published'
        )
        creator_storefront.create_product(
            'solutions','main',title='Draft',
            product_type='service',status='draft'
        )
        rows=creator_storefront.list_products(
            'solutions','main',published_only=True
        )
        self.assertEqual(
            [first.id,second.id,third.id],
            [row.id for row in rows]
        )

    def test_cross_site_and_cross_tenant_access_fail_closed(self):
        tenant_sites.create_site('solutions',slug='creator',name='Creator')
        product=creator_storefront.create_product(
            'solutions','creator',title='Private',
            product_type='service'
        )
        self.assertIsNone(
            creator_storefront.get_product('solutions','main',product.id)
        )
        self.assertIsNone(
            creator_storefront.get_product('personal-training','main',product.id)
        )
        self.assertIsNone(
            creator_storefront.update_product(
                'personal-training','main',product.id,title='Wrong'
            )
        )

    def test_archived_product_is_immutable_and_hidden(self):
        product=creator_storefront.create_product(
            'solutions','main',title='Archive',
            product_type='service'
        )
        archived=creator_storefront.archive_product(
            'solutions','main',product.id
        )
        self.assertEqual('archived',archived.status)
        self.assertEqual([],creator_storefront.list_products('solutions','main'))
        with self.assertRaises(ValueError):
            creator_storefront.update_product(
                'solutions','main',product.id,title='Nope'
            )

    def test_catalog_has_no_transactional_state(self):
        product=creator_storefront.create_product(
            'solutions','main',title='Catalog only',
            product_type='service',price_cents=5000
        )
        for field in ('checkout_url','payment_provider','invoice_id','tax_cents','subscription_id'):
            self.assertFalse(hasattr(product,field))

    def test_archived_site_cannot_be_modified(self):
        tenant_sites.create_site('solutions',slug='seasonal',name='Seasonal')
        tenant_sites.archive_site('solutions','seasonal')
        with self.assertRaises(ValueError):
            creator_storefront.create_product(
                'solutions','seasonal',title='Nope',
                product_type='service'
            )


if __name__=='__main__':
    unittest.main()
