from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import site_forms
import site_services
import tenant_auth
import tenant_sites


class Sprint3ServicesPublicFormsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

    def tearDown(self):
        self.tmp.cleanup()

    def test_services_are_site_scoped_and_publishable(self):
        tenant_sites.create_site('solutions', slug='campaign', name='Campaign')
        site_services.create_service('solutions','main',slug='aws',name='AWS',status='published',position=20)
        site_services.create_service('solutions','campaign',slug='aws',name='Campaign AWS',status='published',position=10)
        self.assertEqual('AWS', site_services.get_service('solutions','main','aws').name)
        self.assertEqual('Campaign AWS', site_services.get_service('solutions','campaign','aws').name)
        self.assertEqual(['aws'], [s.slug for s in site_services.list_services('solutions','main',published_only=True)])

    def test_cross_tenant_service_access_fails(self):
        site_services.create_service('solutions','main',slug='private',name='Private')
        self.assertIsNone(site_services.get_service('personal-training','main','private'))
        self.assertIsNone(site_services.update_service('personal-training','main','private',name='Wrong'))

    def test_duplicate_service_slug_rejected_within_site(self):
        site_services.create_service('solutions','main',slug='aws',name='AWS')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            site_services.create_service('solutions','main',slug='aws',name='Duplicate')

    def test_archived_service_is_hidden_and_immutable(self):
        site_services.create_service('solutions','main',slug='old',name='Old')
        site_services.archive_service('solutions','main','old')
        self.assertEqual([], site_services.list_services('solutions','main'))
        with self.assertRaises(ValueError):
            site_services.update_service('solutions','main','old',name='Nope')

    def test_form_fields_round_trip_and_validation(self):
        form = site_forms.create_form(
            'solutions','main',slug='project-request',title='Project Request',status='published',
            fields=[
                {'name':'email','label':'Email','type':'email','required':True},
                {'name':'service','label':'Service','type':'select','required':True,'options':['AWS','Linux']},
                {'name':'message','label':'Message','type':'textarea','required':True},
            ],
        )
        self.assertEqual('project-request', form.slug)
        self.assertEqual('AWS', form.fields[1]['options'][0])
        self.assertEqual(['project-request'], [f.slug for f in site_forms.list_forms('solutions','main',published_only=True)])

    def test_invalid_form_field_definitions_rejected(self):
        invalid = [
            [{'name':'Bad Name','label':'Bad','type':'text'}],
            [{'name':'field','label':'','type':'text'}],
            [{'name':'field','label':'Field','type':'number'}],
            [{'name':'choice','label':'Choice','type':'select','options':[]}],
            [{'name':'dup','label':'One','type':'text'},{'name':'dup','label':'Two','type':'text'}],
        ]
        for fields in invalid:
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError):
                    site_forms.create_form('solutions','main',slug='form',title='Form',fields=fields)

    def test_forms_are_cross_tenant_isolated(self):
        site_forms.create_form('solutions','main',slug='contact',title='Contact',fields=[])
        self.assertIsNone(site_forms.get_form('personal-training','main','contact'))
        self.assertIsNone(site_forms.update_form('personal-training','main','contact',title='Wrong'))

    def test_archived_form_and_site_cannot_be_modified(self):
        site_forms.create_form('solutions','main',slug='old',title='Old',fields=[])
        site_forms.archive_form('solutions','main','old')
        with self.assertRaises(ValueError):
            site_forms.update_form('solutions','main','old',title='Nope')
        tenant_sites.create_site('solutions',slug='seasonal',name='Seasonal')
        tenant_sites.archive_site('solutions','seasonal')
        with self.assertRaises(ValueError):
            site_forms.create_form('solutions','seasonal',slug='x',title='X',fields=[])

    def test_existing_static_form_config_is_not_required_by_site_models(self):
        # S3-T06 is additive; the live request intake remains untouched until migration/rendering.
        self.assertEqual([], site_forms.list_forms('solutions','main'))


if __name__ == '__main__':
    unittest.main()
