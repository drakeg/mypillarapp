from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import billing_admin
import billing_checkout
import billing_plans
import billing_provider
import tenant_auth
import tenant_sites


class FakeProvider:
    provider_name = 'stripe'

    def execute(self, request):
        if request.operation == 'customer.create':
            return billing_provider.ProviderResponse(
                'stripe', request.operation, 'cus_admin', 'customer', ''
            )
        if request.operation == 'checkout_session.create':
            return billing_provider.ProviderResponse(
                'stripe',
                request.operation,
                'cs_admin',
                'checkout.session',
                'open',
                'https://checkout.stripe.com/c/pay/cs_admin',
            )
        raise AssertionError(request.operation)


class Sprint8BillingAdminTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()
        self.owner = self._user('solutions', 'owner@example.com', 'owner')
        self.admin = self._user('solutions', 'admin@example.com', 'admin')
        self.staff = self._user('solutions', 'staff@example.com', 'staff')
        self.other = self._user('adventures', 'other@example.com', 'owner')
        billing_plans.create_plan(
            self.owner,
            'solutions',
            slug='starter',
            name='Starter',
            entitlements={
                'sites': 2,
                'crm': True,
                'portal': True,
                'creator': False,
                'ai': False,
                'ai_rolling_units': 0,
            },
        )

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
                    now, now, org['id'], email, 'Billing', 'Admin',
                    tenant_auth.hash_password('abcdefghijkl'), role,
                ),
            )
            uid = int(cur.lastrowid)
            conn.execute(
                '''INSERT INTO auth_memberships(
                       created_at,updated_at,user_id,organization_id,
                       role_id,status
                   ) VALUES(?,?,?,?,?,'active')''',
                (now, now, uid, org['id'], role_row['id']),
            )
            conn.commit()
        return uid

    def test_owner_and_admin_can_read_billing_overview(self):
        owner = billing_admin.overview(self.owner, 'solutions')
        admin = billing_admin.overview(self.admin, 'solutions')
        self.assertEqual('solutions', owner.organization_slug)
        self.assertEqual('solutions', admin.organization_slug)
        self.assertEqual('starter', owner.available_plans[0].slug)

    def test_staff_cannot_read_or_mutate_billing(self):
        with self.assertRaises(PermissionError):
            billing_admin.overview(self.staff, 'solutions')
        with self.assertRaises(PermissionError):
            billing_admin.assign_plan(
                self.staff, 'solutions', 'starter'
            )

    def test_cross_tenant_billing_read_fails_closed(self):
        with self.assertRaises(PermissionError):
            billing_admin.overview(self.other, 'solutions')

    def test_assign_plan_updates_overview(self):
        overview = billing_admin.assign_plan(
            self.owner, 'solutions', 'starter'
        )
        self.assertIsNotNone(overview.assignment)
        self.assertEqual('starter', overview.assignment.plan_slug)

    def test_provider_price_configuration_stays_tenant_scoped(self):
        overview = billing_admin.configure_provider_price(
            self.owner,
            'solutions',
            plan_slug='starter',
            provider_name='stripe',
            price_ref='price_starter',
        )
        self.assertEqual('solutions', overview.organization_slug)
        price = billing_checkout.get_plan_price(
            'solutions', 'starter', 'stripe'
        )
        self.assertEqual('price_starter', price.price_ref)
        self.assertIsNone(
            billing_checkout.get_plan_price(
                'adventures', 'starter', 'stripe'
            )
        )

    def test_checkout_helper_requires_billing_admin_scope(self):
        billing_admin.configure_provider_price(
            self.owner,
            'solutions',
            plan_slug='starter',
            provider_name='stripe',
            price_ref='price_starter',
        )
        provider = FakeProvider()
        checkout = billing_admin.create_checkout(
            self.admin,
            'solutions',
            provider=provider,
            plan_slug='starter',
            customer_email='owner@example.com',
            customer_name='Example LLC',
            success_url='https://billing.example.com/success',
            cancel_url='https://billing.example.com/cancel',
            allowed_return_hosts={'billing.example.com'},
        )
        self.assertEqual('pending', checkout.status)

        with self.assertRaises(PermissionError):
            billing_admin.create_checkout(
                self.staff,
                'solutions',
                provider=provider,
                plan_slug='starter',
                customer_email='staff@example.com',
                customer_name='Staff User',
                success_url='https://billing.example.com/success',
                cancel_url='https://billing.example.com/cancel',
                allowed_return_hosts={'billing.example.com'},
            )


if __name__ == '__main__':
    unittest.main()
