from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import site_media
import tenant_auth
import tenant_sites


class Sprint3MediaFoundationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

    def tearDown(self):
        self.tmp.cleanup()

    def test_media_is_site_scoped(self):
        tenant_sites.create_site('solutions', slug='campaign', name='Campaign')
        site_media.create_media(
            'solutions','main',slug='hero',kind='image',
            source='/assets/hero.png',alt_text='Main hero',status='published'
        )
        site_media.create_media(
            'solutions','campaign',slug='hero',kind='image',
            source='https://cdn.example.com/campaign.png',alt_text='Campaign hero',status='published'
        )
        self.assertEqual('Main hero', site_media.get_media('solutions','main','hero').alt_text)
        self.assertEqual('Campaign hero', site_media.get_media('solutions','campaign','hero').alt_text)

    def test_cross_tenant_lookup_and_update_fail(self):
        site_media.create_media('solutions','main',slug='private',kind='document',source='/docs/private.pdf')
        self.assertIsNone(site_media.get_media('personal-training','main','private'))
        self.assertIsNone(
            site_media.update_media('personal-training','main','private',alt_text='Wrong')
        )

    def test_duplicate_slug_rejected_within_site(self):
        site_media.create_media('solutions','main',slug='logo',kind='image',source='/logo.png')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            site_media.create_media('solutions','main',slug='logo',kind='image',source='/other.png')

    def test_safe_source_validation(self):
        allowed = ['/assets/file.png', 'https://example.com/file.png', 'http://example.com/file.png']
        for i, source in enumerate(allowed):
            site_media.create_media('solutions','main',slug=f'allowed-{i}',kind='image',source=source)
        for i, source in enumerate(['', '//evil.example/file', 'javascript:alert(1)', 'ftp://example.com/file']):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    site_media.create_media('solutions','main',slug=f'bad-{i}',kind='image',source=source)

    def test_kind_and_mime_type_validation(self):
        with self.assertRaises(ValueError):
            site_media.create_media('solutions','main',slug='bad-kind',kind='binary',source='/file.bin')
        with self.assertRaises(ValueError):
            site_media.create_media('solutions','main',slug='bad-mime',kind='image',source='/file.png',mime_type='png')
        item = site_media.create_media('solutions','main',slug='good-mime',kind='image',source='/file.png',mime_type='image/png')
        self.assertEqual('image/png', item.mime_type)

    def test_published_and_kind_filters(self):
        site_media.create_media('solutions','main',slug='img-live',kind='image',source='/a.png',status='published')
        site_media.create_media('solutions','main',slug='img-draft',kind='image',source='/b.png',status='draft')
        site_media.create_media('solutions','main',slug='doc-live',kind='document',source='/a.pdf',status='published')
        self.assertEqual(
            ['img-live'],
            [m.slug for m in site_media.list_media('solutions','main',published_only=True,kind='image')],
        )

    def test_archived_media_is_hidden_and_immutable(self):
        site_media.create_media('solutions','main',slug='old',kind='image',source='/old.png')
        site_media.archive_media('solutions','main','old')
        self.assertEqual([], site_media.list_media('solutions','main'))
        with self.assertRaises(ValueError):
            site_media.update_media('solutions','main','old',alt_text='Nope')

    def test_archived_site_cannot_receive_or_update_media(self):
        tenant_sites.create_site('solutions',slug='seasonal',name='Seasonal')
        site_media.create_media('solutions','seasonal',slug='hero',kind='image',source='/hero.png')
        tenant_sites.archive_site('solutions','seasonal')
        with self.assertRaises(ValueError):
            site_media.create_media('solutions','seasonal',slug='new',kind='image',source='/new.png')
        with self.assertRaises(ValueError):
            site_media.update_media('solutions','seasonal','hero',alt_text='Nope')


if __name__ == '__main__':
    unittest.main()
