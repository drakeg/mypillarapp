from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import billing_boundary
import creator_storefront
import crm_quotes
import tenant_auth
import tenant_sites


class Sprint8BillingBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()
        self.owner = self._user('solutions', 'owner@example.com', 'owner')
        self.staff = self._user('solutions', 'staff@example.com', 'staff')
        self.other_owner = self._user(
            'adventures', 'other@example.com', 'owner'
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _user(self, organization_slug, email, role):
        with tenant_auth.db() as conn:
            org = conn.execute(
                'SELECT id FROM auth_organizations WHERE slug=?',
                (organization_slug,),
            ).fetchone()
            role_row = conn.execute(
                'SELECT id FROM auth_roles WHERE slug=?',
                (role,),
            ).fetchone()
            now = tenant_auth.now()
            cur = conn.execute(
                '''INSERT INTO auth_users(
                       created_at,updated_at,organization_id,email,
                       first_name,last_name,password_hash,role,is_active
                   ) VALUES(?,?,?,?,?,?,?,?,1)''',
                (
                    now, now, org['id'], email, 'Billing', 'User',
                    tenant_auth.hash_password('abcdefghijkl'), role,
                ),
            )
            user_id = int(cur.lastrowid)
            conn.execute(
                '''INSERT INTO auth_memberships(
                       created_at,updated_at,user_id,organization_id,
                       role_id,status
                   ) VALUES(?,?,?,?,?,'active')''',
                (now, now, user_id, org['id'], role_row['id']),
            )
            conn.commit()
        return user_id

    def test_billing_data_classification_blocks_payment_credentials(self):
        self.assertEqual(
            'eligible',
            billing_boundary.classify_billing_data('subscription'),
        )
        for data_class in (
            'card_number',
            'card_cvc',
            'bank_account_number',
            'payment_provider_secret',
            'webhook_secret',
            'raw_payment_method',
        ):
            self.assertEqual(
                'prohibited',
                billing_boundary.classify_billing_data(data_class),
            )
        self.assertEqual(
            'unknown',
            billing_boundary.classify_billing_data('mystery'),
        )

    def test_scope_requires_active_explicit_membership(self):
        scope = billing_boundary.authorize_scope(
            self.owner, 'solutions'
        )
        self.assertEqual('solutions', scope.organization_slug)
        self.assertEqual('owner', scope.role)

        with self.assertRaises(PermissionError):
            billing_boundary.authorize_scope(
                self.other_owner, 'solutions'
            )

    def test_billing_admin_is_owner_admin_only(self):
        billing_boundary.authorize_billing_admin(
            self.owner, 'solutions'
        )
        with self.assertRaises(PermissionError):
            billing_boundary.authorize_billing_admin(
                self.staff, 'solutions'
            )

    def test_provider_references_are_opaque_bounded_identifiers(self):
        self.assertEqual(
            'cus_123',
            billing_boundary.validate_provider_reference(' cus_123 '),
        )
        with self.assertRaises(ValueError):
            billing_boundary.validate_provider_reference('')
        with self.assertRaises(ValueError):
            billing_boundary.validate_provider_reference('x' * 256)
        with self.assertRaises(ValueError):
            billing_boundary.validate_provider_reference('cus_123\nsecret')

    def test_same_tenant_quote_is_eligible_but_cannot_authorize_charge(self):
        quote = crm_quotes.create_quote(
            'solutions',
            title='Implementation quote',
        )
        scope = billing_boundary.authorize_scope(
            self.owner, 'solutions'
        )
        ref = billing_boundary.LegacyPriceReference(
            'crm_quote', str(quote.id)
        )
        billing_boundary.validate_legacy_price_reference(scope, ref)
        self.assertFalse(
            billing_boundary.legacy_price_can_authorize_charge(ref)
        )

    def test_cross_tenant_quote_fails_closed(self):
        quote = crm_quotes.create_quote(
            'adventures',
            title='Foreign quote',
        )
        scope = billing_boundary.authorize_scope(
            self.owner, 'solutions'
        )
        with self.assertRaises(PermissionError):
            billing_boundary.validate_legacy_price_reference(
                scope,
                billing_boundary.LegacyPriceReference(
                    'crm_quote', str(quote.id)
                ),
            )

    def test_storefront_product_requires_same_tenant_site(self):
        product = creator_storefront.create_product(
            'adventures',
            'main',
            title='Foreign product',
            product_type='service',
            price_cents=1000,
        )
        scope = billing_boundary.authorize_scope(
            self.owner, 'solutions'
        )
        with self.assertRaises(PermissionError):
            billing_boundary.validate_legacy_price_reference(
                scope,
                billing_boundary.LegacyPriceReference(
                    'storefront_product',
                    str(product.id),
                    site_slug='main',
                ),
            )

    def test_service_price_text_and_provider_state_never_authorize_access(self):
        scope = billing_boundary.authorize_scope(
            self.owner, 'solutions'
        )
        ref = billing_boundary.LegacyPriceReference(
            'site_service_price_text',
            'aws-cloud-setup',
            site_slug='main',
        )
        with self.assertRaises(PermissionError):
            billing_boundary.validate_legacy_price_reference(scope, ref)
        self.assertFalse(
            billing_boundary.legacy_price_can_authorize_charge(ref)
        )
        self.assertFalse(
            billing_boundary.provider_state_can_authorize_access()
        )


if __name__ == '__main__':
    unittest.main()
