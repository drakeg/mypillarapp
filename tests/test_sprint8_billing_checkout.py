from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import billing_checkout
import billing_plans
import billing_provider
import tenant_auth
import tenant_sites


class FakeProvider:
    provider_name = 'stripe'

    def __init__(self):
        self.calls = []
        self.customer_number = 0
        self.checkout_number = 0

    def execute(self, request):
        self.calls.append(request)
        if request.operation == 'customer.create':
            self.customer_number += 1
            return billing_provider.ProviderResponse(
                provider_name='stripe',
                operation=request.operation,
                object_id=f'cus_{self.customer_number}',
                object_type='customer',
                raw_status='',
            )
        if request.operation == 'checkout_session.create':
            self.checkout_number += 1
            return billing_provider.ProviderResponse(
                provider_name='stripe',
                operation=request.operation,
                object_id=f'cs_{self.checkout_number}',
                object_type='checkout.session',
                raw_status='open',
                redirect_url=f'https://checkout.stripe.com/c/pay/cs_{self.checkout_number}',
            )
        raise AssertionError(request.operation)


class Sprint8CheckoutOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()

        self.owner = self._user(
            'solutions', 'owner@example.com', 'owner'
        )
        self.admin = self._user(
            'solutions', 'admin@example.com', 'admin'
        )
        self.staff = self._user(
            'solutions', 'staff@example.com', 'staff'
        )
        self.other_owner = self._user(
            'adventures', 'other@example.com', 'owner'
        )

        billing_plans.create_plan(
            self.owner,
            'solutions',
            slug='starter',
            name='Starter',
            entitlements={'sites': 2, 'crm': True},
        )
        billing_plans.create_plan(
            self.other_owner,
            'adventures',
            slug='starter',
            name='Adventure Starter',
            entitlements={'sites': 1},
        )
        self.provider = FakeProvider()

    def tearDown(self):
        self.tmp.cleanup()

    def _user(self, org_slug, email, role):
        with tenant_auth.db() as conn:
            org = conn.execute(
                'SELECT id FROM auth_organizations WHERE slug=?',
                (org_slug,),
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
                    now,
                    now,
                    org['id'],
                    email,
                    'Checkout',
                    'User',
                    tenant_auth.hash_password('abcdefghijkl'),
                    role,
                ),
            )
            user_id = int(cur.lastrowid)
            conn.execute(
                '''INSERT INTO auth_memberships(
                       created_at,updated_at,user_id,organization_id,
                       role_id,status
                   ) VALUES(?,?,?,?,?,'active')''',
                (
                    now,
                    now,
                    user_id,
                    org['id'],
                    role_row['id'],
                ),
            )
            conn.commit()
        return user_id

    def _configure_price(self):
        return billing_checkout.configure_plan_price(
            self.owner,
            'solutions',
            plan_slug='starter',
            provider_name='stripe',
            price_ref='price_starter',
        )

    def _checkout(self, user_id=None):
        return billing_checkout.create_checkout_session(
            user_id or self.owner,
            'solutions',
            provider=self.provider,
            plan_slug='starter',
            customer_email='owner@example.com',
            customer_name='Example LLC',
            success_url='https://billing.example.com/success',
            cancel_url='https://billing.example.com/cancel',
            allowed_return_hosts={'billing.example.com'},
        )

    def test_plan_price_mapping_is_tenant_scoped(self):
        price = self._configure_price()
        self.assertEqual('solutions', price.organization_slug)
        self.assertEqual('starter', price.plan_slug)
        self.assertEqual('price_starter', price.price_ref)
        self.assertIsNone(
            billing_checkout.get_plan_price(
                'adventures', 'starter', 'stripe'
            )
        )

    def test_staff_cannot_configure_price_or_create_checkout(self):
        with self.assertRaises(PermissionError):
            billing_checkout.configure_plan_price(
                self.staff,
                'solutions',
                plan_slug='starter',
                provider_name='stripe',
                price_ref='price_starter',
            )
        self._configure_price()
        with self.assertRaises(PermissionError):
            self._checkout(self.staff)

    def test_checkout_requires_provider_price_mapping(self):
        with self.assertRaises(ValueError):
            self._checkout()
        self.assertEqual([], self.provider.calls)

    def test_checkout_creates_tenant_customer_and_pending_session(self):
        self._configure_price()
        checkout = self._checkout()
        self.assertEqual('solutions', checkout.organization_slug)
        self.assertEqual('starter', checkout.plan_slug)
        self.assertEqual('stripe', checkout.provider_name)
        self.assertEqual('cus_1', checkout.customer_ref)
        self.assertEqual('cs_1', checkout.session_ref)
        self.assertEqual('pending', checkout.status)
        self.assertTrue(
            checkout.checkout_url.startswith(
                'https://checkout.stripe.com/'
            )
        )

        operations = [call.operation for call in self.provider.calls]
        self.assertEqual(
            ['customer.create', 'checkout_session.create'],
            operations,
        )

    def test_existing_customer_is_reused(self):
        self._configure_price()
        self._checkout()
        second = self._checkout()
        self.assertEqual('cus_1', second.customer_ref)
        operations = [call.operation for call in self.provider.calls]
        self.assertEqual(
            [
                'customer.create',
                'checkout_session.create',
                'checkout_session.create',
            ],
            operations,
        )

    def test_return_urls_must_be_https_and_allowlisted(self):
        self._configure_price()
        with self.assertRaises(ValueError):
            billing_checkout.create_checkout_session(
                self.owner,
                'solutions',
                provider=self.provider,
                plan_slug='starter',
                customer_email='owner@example.com',
                customer_name='Example LLC',
                success_url='http://billing.example.com/success',
                cancel_url='https://billing.example.com/cancel',
                allowed_return_hosts={'billing.example.com'},
            )
        with self.assertRaises(ValueError):
            billing_checkout.create_checkout_session(
                self.owner,
                'solutions',
                provider=self.provider,
                plan_slug='starter',
                customer_email='owner@example.com',
                customer_name='Example LLC',
                success_url='https://evil.example/success',
                cancel_url='https://billing.example.com/cancel',
                allowed_return_hosts={'billing.example.com'},
            )
        self.assertEqual([], self.provider.calls)

    def test_provider_response_does_not_assign_plan_or_enable_entitlement(self):
        self._configure_price()
        before = billing_plans.get_assignment('solutions')
        self.assertIsNone(before)

        self._checkout()

        after = billing_plans.get_assignment('solutions')
        self.assertIsNone(after)
        creator = billing_plans.entitlement('solutions', 'creator')
        self.assertEqual('internal_default', creator.source)

    def test_checkout_lookup_is_tenant_scoped(self):
        self._configure_price()
        checkout = self._checkout()
        self.assertIsNone(
            billing_checkout.get_checkout_session(
                'adventures', checkout.id
            )
        )

    def test_cross_tenant_plan_price_cannot_be_used(self):
        billing_checkout.configure_plan_price(
            self.other_owner,
            'adventures',
            plan_slug='starter',
            provider_name='stripe',
            price_ref='price_adventure',
        )
        with self.assertRaises(ValueError):
            self._checkout()
        self.assertEqual([], self.provider.calls)

    def test_provider_checkout_url_must_be_https(self):
        class BadProvider(FakeProvider):
            def execute(self, request):
                if request.operation == 'customer.create':
                    return super().execute(request)
                return billing_provider.ProviderResponse(
                    provider_name='stripe',
                    operation=request.operation,
                    object_id='cs_bad',
                    object_type='checkout.session',
                    raw_status='open',
                    redirect_url='http://checkout.example/unsafe',
                )

        self._configure_price()
        with self.assertRaises(billing_provider.BillingProviderError):
            billing_checkout.create_checkout_session(
                self.owner,
                'solutions',
                provider=BadProvider(),
                plan_slug='starter',
                customer_email='owner@example.com',
                customer_name='Example LLC',
                success_url='https://billing.example.com/success',
                cancel_url='https://billing.example.com/cancel',
                allowed_return_hosts={'billing.example.com'},
            )


if __name__ == '__main__':
    unittest.main()
