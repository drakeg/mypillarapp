from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import creator_downloads
import tenant_auth
import tenant_sites


class Sprint6CreatorDownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        data=Path(self.tmp.name)
        tenant_auth.DATA_DIR=data
        tenant_auth.DB_PATH=data/'madmallard.sqlite3'
        tenant_sites.ensure_schema()

    def tearDown(self):
        self.tmp.cleanup()

    def test_external_https_download_metadata(self):
        row=creator_downloads.create_download(
            'solutions','main',
            title='Travel checklist',
            description='Printable checklist',
            version='1.0',
            source_type='external_url',
            source_ref='https://example.com/checklist.pdf',
            file_name='checklist.pdf',
            mime_type='application/pdf',
            visibility='public',
            status='published',
        )
        self.assertEqual('1.0',row.version)
        self.assertEqual('https://example.com/checklist.pdf',creator_downloads.public_source(row))

    def test_storage_key_is_opaque_and_never_public_source(self):
        row=creator_downloads.create_download(
            'solutions','main',
            title='Private guide',
            source_type='storage_key',
            source_ref='downloads/guides/private-guide.pdf',
            visibility='public',
            status='published',
        )
        self.assertEqual('downloads/guides/private-guide.pdf',row.source_ref)
        self.assertIsNone(creator_downloads.public_source(row))

    def test_unsafe_sources_are_rejected(self):
        bad_external=('http://example.com/x','https://u:p@example.com/x','file:///tmp/x')
        for value in bad_external:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    creator_downloads.create_download(
                        'solutions','main',title='Bad',
                        source_type='external_url',source_ref=value
                    )
        for value in ('/etc/passwd','../secret','downloads//bad','file:secret'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    creator_downloads.create_download(
                        'solutions','main',title='Bad',
                        source_type='storage_key',source_ref=value
                    )

    def test_visibility_and_published_filters(self):
        public=creator_downloads.create_download(
            'solutions','main',title='Public',
            source_type='external_url',source_ref='https://example.com/public',
            visibility='public',status='published'
        )
        creator_downloads.create_download(
            'solutions','main',title='Customer',
            source_type='external_url',source_ref='https://example.com/customer',
            visibility='customer',status='published'
        )
        creator_downloads.create_download(
            'solutions','main',title='Draft',
            source_type='external_url',source_ref='https://example.com/draft',
            visibility='public',status='draft'
        )
        rows=creator_downloads.list_downloads(
            'solutions','main',published_only=True,visibility='public'
        )
        self.assertEqual([public.id],[row.id for row in rows])

    def test_cross_tenant_and_site_access_fail_closed(self):
        tenant_sites.create_site('solutions',slug='creator',name='Creator')
        row=creator_downloads.create_download(
            'solutions','creator',title='Private',
            source_type='storage_key',source_ref='downloads/private/file.zip'
        )
        self.assertIsNone(
            creator_downloads.get_download('solutions','main',row.id)
        )
        self.assertIsNone(
            creator_downloads.get_download('personal-training','main',row.id)
        )
        self.assertIsNone(
            creator_downloads.update_download(
                'personal-training','main',row.id,title='Wrong'
            )
        )

    def test_archived_download_is_immutable_and_hidden(self):
        row=creator_downloads.create_download(
            'solutions','main',title='Archive',
            source_type='storage_key',source_ref='downloads/archive/file.zip'
        )
        archived=creator_downloads.archive_download('solutions','main',row.id)
        self.assertEqual('archived',archived.status)
        self.assertEqual([],creator_downloads.list_downloads('solutions','main'))
        with self.assertRaises(ValueError):
            creator_downloads.update_download(
                'solutions','main',row.id,title='Nope'
            )

    def test_catalog_presence_does_not_create_entitlement_fields(self):
        row=creator_downloads.create_download(
            'solutions','main',title='Free metadata',
            source_type='storage_key',source_ref='downloads/free/file.zip'
        )
        self.assertFalse(hasattr(row,'price_cents'))
        self.assertFalse(hasattr(row,'entitled'))
        self.assertFalse(hasattr(row,'payment_provider'))

    def test_archived_site_cannot_be_modified(self):
        tenant_sites.create_site('solutions',slug='seasonal',name='Seasonal')
        tenant_sites.archive_site('solutions','seasonal')
        with self.assertRaises(ValueError):
            creator_downloads.create_download(
                'solutions','seasonal',title='Nope',
                source_type='storage_key',source_ref='downloads/nope/file.zip'
            )


if __name__ == '__main__':
    unittest.main()
