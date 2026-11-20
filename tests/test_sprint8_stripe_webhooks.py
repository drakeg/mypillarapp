from __future__ import annotations

import hashlib
import hmac
import json
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
import billing_subscriptions
import stripe_webhooks
import tenant_auth
import tenant_sites


class FakeProvider:
    provider_name = 'stripe'

    def execute(self, request):
        if request.operation == 'customer.create':
            return billing_provider.ProviderResponse(
                'stripe', request.operation, 'cus_1', 'customer', ''
            )
        if request.operation == 'checkout_session.create':
            return billing_provider.ProviderResponse(
                'stripe',
                request.operation,
                'cs_1',
                'checkout.session',
                'open',
                'https://checkout.stripe.com/c/pay/cs_1',
            )
        raise AssertionError(request.operation)


class Sprint8StripeWebhookTests(unittest.TestCase):
    secret = 'whsec_test'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()
        self.owner = self._user('solutions', 'owner@example.com', 'owner')
        self.other = self._user('adventures', 'other@example.com', 'owner')
        billing_plans.create_plan(
            self.owner,
            'solutions',
            slug='starter',
            name='Starter',
            entitlements={'sites': 2, 'crm': True},
        )
        billing_checkout.configure_plan_price(
            self.owner,
            'solutions',
            plan_slug='starter',
            provider_name='stripe',
            price_ref='price_starter',
        )
        self.provider = FakeProvider()
        self.checkout = billing_checkout.create_checkout_session(
            self.owner,
            'solutions',
            provider=self.provider,
            plan_slug='starter',
            customer_email='owner@example.com',
            customer_name='Example LLC',
            success_url='https://billing.example.com/success',
            cancel_url='https://billing.example.com/cancel',
            allowed_return_hosts={'billing.example.com'},
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
                    now, now, org['id'], email, 'Webhook', 'User',
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

    def _payload(self, event):
        return json.dumps(event, separators=(',', ':')).encode()

    def _signature(self, payload, timestamp):
        digest = hmac.new(
            self.secret.encode(),
            str(timestamp).encode() + b'.' + payload,
            hashlib.sha256,
        ).hexdigest()
        return f't={timestamp},v1={digest}'

    def _checkout_event(self, event_id='evt_checkout', created=1000, org='solutions'):
        return {
            'id': event_id,
            'type': 'checkout.session.completed',
            'created': created,
            'data': {'object': {
                'id': 'cs_1',
                'customer': 'cus_1',
                'subscription': 'sub_1',
                'metadata': {'organization_slug': org},
            }},
        }

    def test_signature_verification_and_stale_rejection(self):
        payload = self._payload(self._checkout_event())
        sig = self._signature(payload, 1000)
        self.assertEqual(
            1000,
            stripe_webhooks.verify_stripe_signature(
                payload, sig, self.secret, now=1000
            ),
        )
        with self.assertRaises(PermissionError):
            stripe_webhooks.verify_stripe_signature(
                payload, sig, self.secret, now=2000
            )
        with self.assertRaises(PermissionError):
            stripe_webhooks.verify_stripe_signature(
                payload, 't=1000,v1=bad', self.secret, now=1000
            )

    def test_verified_checkout_reconciles_subscription_and_entitlement_plan(self):
        event = self._checkout_event()
        payload = self._payload(event)
        result = stripe_webhooks.process_stripe_event(
            payload,
            self._signature(payload, 1000),
            self.secret,
            now=1000,
        )
        self.assertEqual('processed', result.status)
        self.assertEqual('solutions', result.organization_slug)

        sub = billing_subscriptions.current_subscription('solutions')
        self.assertIsNotNone(sub)
        self.assertEqual('active', sub.status)
        self.assertEqual('sub_1', sub.provider_subscription_ref)
        assignment = billing_plans.get_assignment('solutions')
        self.assertEqual('starter', assignment.plan_slug)

    def test_duplicate_event_is_idempotent(self):
        event = self._checkout_event()
        payload = self._payload(event)
        sig = self._signature(payload, 1000)
        stripe_webhooks.process_stripe_event(
            payload, sig, self.secret, now=1000
        )
        second = stripe_webhooks.process_stripe_event(
            payload, sig, self.secret, now=1000
        )
        self.assertTrue(second.duplicate)
        self.assertEqual(
            1, len(billing_subscriptions.list_subscriptions('solutions'))
        )

    def test_metadata_tenant_mismatch_is_rejected(self):
        event = self._checkout_event(org='adventures')
        payload = self._payload(event)
        with self.assertRaises(PermissionError):
            stripe_webhooks.process_stripe_event(
                payload,
                self._signature(payload, 1000),
                self.secret,
                now=1000,
            )
        self.assertIsNone(
            billing_subscriptions.current_subscription('solutions')
        )

    def test_out_of_order_subscription_event_is_ignored(self):
        event = self._checkout_event(created=1000)
        payload = self._payload(event)
        stripe_webhooks.process_stripe_event(
            payload,
            self._signature(payload, 1000),
            self.secret,
            now=1000,
        )

        update = {
            'id': 'evt_sub_old',
            'type': 'customer.subscription.updated',
            'created': 900,
            'data': {'object': {
                'id': 'sub_1',
                'customer': 'cus_1',
                'status': 'past_due',
                'metadata': {'organization_slug': 'solutions'},
            }},
        }
        old_payload = self._payload(update)
        result = stripe_webhooks.process_stripe_event(
            old_payload,
            self._signature(old_payload, 900),
            self.secret,
            now=900,
        )
        self.assertEqual('ignored', result.status)
        self.assertEqual(
            'active',
            billing_subscriptions.current_subscription('solutions').status,
        )

    def test_newer_subscription_event_updates_local_state(self):
        event = self._checkout_event(created=1000)
        payload = self._payload(event)
        stripe_webhooks.process_stripe_event(
            payload,
            self._signature(payload, 1000),
            self.secret,
            now=1000,
        )

        update = {
            'id': 'evt_sub_new',
            'type': 'customer.subscription.updated',
            'created': 1100,
            'data': {'object': {
                'id': 'sub_1',
                'customer': 'cus_1',
                'status': 'past_due',
                'metadata': {'organization_slug': 'solutions'},
            }},
        }
        new_payload = self._payload(update)
        result = stripe_webhooks.process_stripe_event(
            new_payload,
            self._signature(new_payload, 1100),
            self.secret,
            now=1100,
        )
        self.assertEqual('processed', result.status)
        self.assertEqual(
            'past_due',
            billing_subscriptions.current_subscription('solutions').status,
        )

    def test_invoice_event_is_safely_ignored_and_audited(self):
        event = {
            'id': 'evt_invoice',
            'type': 'invoice.paid',
            'created': 1000,
            'data': {'object': {'id': 'in_1'}},
        }
        payload = self._payload(event)
        result = stripe_webhooks.process_stripe_event(
            payload,
            self._signature(payload, 1000),
            self.secret,
            now=1000,
        )
        self.assertEqual('ignored', result.status)
        self.assertEqual(
            'invoice_event_deferred_to_s8_t07',
            result.detail,
        )


if __name__ == '__main__':
    unittest.main()
