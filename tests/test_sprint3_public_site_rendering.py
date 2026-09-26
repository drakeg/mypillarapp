from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import public_site_renderer
import site_branding
import site_forms
import site_navigation
import site_pages
import site_services
import tenant_auth
import tenant_context
import tenant_sites


class Sprint3PublicSiteRenderingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

        tenant_sites.create_site(
            'personal-training',
            slug='landing',
            name='Training Landing',
            status='published',
        )
        self.assertTrue(
            tenant_context.register_domain(
                'personal-training',
                'training.example.test',
                site_slug='landing',
            )
        )
        site_branding.update_branding(
            'personal-training',
            'landing',
            site_name='Training Site',
            tagline='Strong & steady',
            primary_color='#123456',
            secondary_color='#abcdef',
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_hostname_selects_correct_published_site(self):
        site_pages.create_page(
            'personal-training','landing',
            slug='about',title='About',summary='About us',body='Body',
            status='published'
        )
        result = public_site_renderer.render_public_path('training.example.test','/')
        self.assertEqual(200, result.status)
        self.assertIn('Training Site', result.body)
        self.assertIn('/pages/about', result.body)

    def test_only_published_content_is_rendered(self):
        site_pages.create_page(
            'personal-training','landing',
            slug='draft',title='Secret draft',body='hidden',status='draft'
        )
        site_services.create_service(
            'personal-training','landing',
            slug='live',name='Live service',status='published'
        )
        site_services.create_service(
            'personal-training','landing',
            slug='draft-service',name='Draft service',status='draft'
        )
        result = public_site_renderer.render_public_path('training.example.test','/')
        self.assertNotIn('Secret draft', result.body)
        self.assertIn('Live service', result.body)
        self.assertNotIn('Draft service', result.body)

    def test_page_body_is_escaped_not_executed(self):
        site_pages.create_page(
            'personal-training','landing',
            slug='safe',title='Safe',body='<script>alert(1)</script>',
            status='published'
        )
        result = public_site_renderer.render_public_path(
            'training.example.test','/pages/safe'
        )
        self.assertEqual(200, result.status)
        self.assertIn('&lt;script&gt;', result.body)
        self.assertNotIn('<script>alert(1)</script>', result.body)

    def test_visible_navigation_only(self):
        site_navigation.create_item(
            'personal-training','landing',label='Visible',target='/pages/visible',is_visible=True
        )
        site_navigation.create_item(
            'personal-training','landing',label='Hidden',target='/pages/hidden',is_visible=False
        )
        result = public_site_renderer.render_public_path('training.example.test','/')
        self.assertIn('Visible', result.body)
        self.assertNotIn('Hidden', result.body)

    def test_published_form_definition_renders_without_submission_action(self):
        site_forms.create_form(
            'personal-training','landing',
            slug='contact',title='Contact',
            fields=[{'name':'email','label':'Email','type':'email','required':True}],
            status='published'
        )
        result = public_site_renderer.render_public_path('training.example.test','/')
        self.assertIn('Contact', result.body)
        self.assertIn('disabled', result.body)
        self.assertNotIn('action=', result.body)

    def test_draft_site_is_not_public(self):
        tenant_sites.create_site(
            'adventures',slug='preview',name='Preview',status='draft'
        )
        tenant_context.register_domain(
            'adventures','preview.example.test',site_slug='preview'
        )
        result = public_site_renderer.render_public_path('preview.example.test','/')
        self.assertEqual(404, result.status)
        self.assertIn('not been published', result.body)

    def test_solutions_main_uses_compatibility_fallback(self):
        result = public_site_renderer.render_public_path(
            tenant_auth.PRIMARY_DOMAIN,'/'
        )
        self.assertIsNone(result)

    def test_unknown_path_returns_404_for_site_builder_site(self):
        result = public_site_renderer.render_public_path(
            'training.example.test','/does-not-exist'
        )
        self.assertEqual(404, result.status)


if __name__ == '__main__':
    unittest.main()
