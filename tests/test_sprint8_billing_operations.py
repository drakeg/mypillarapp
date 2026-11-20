from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import billing_checkout
import billing_operations
import billing_plans
import billing_provider
import tenant_auth
import tenant_sites


class FakeProvider:
    provider_name = 'stripe'

    def __init__(self):
        self.calls = []

    def execute(self, request):
        self.calls.append(request.operation)
        if request.operation == 'customer.create':
            return billing_provider.ProviderResponse(
                'stripe', request.operation, 'cus_retry', 'customer', ''
            )
        if request.operation == 'checkout_session.create':
            return billing_provider.ProviderResponse(
                'stripe', request.operation, 'cs_retry',
                'checkout.session', 'open',
                'https://checkout.stripe.com/c/pay/cs_retry',
            )
        raise AssertionError(request.operation)


class Sprint8BillingOperationsTests(unittest.TestCase):
    secret = 'whsec_ops'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()
        self.owner = self._user('solutions', 'owner@example.com', 'owner')
        self.staff = self._user('solutions', 'staff@example.com', 'staff')
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
                    now, now, org['id'], email, 'Ops', 'User',
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

    def _payload(self, *, object_ref='cs_retry'):
        event = {
            'id': 'evt_retry',
            'type': 'checkout.session.completed',
            'created': 1000,
            'data': {'object': {
                'id': object_ref,
                'customer': 'cus_retry',
                'subscription': 'sub_retry',
                'metadata': {'organization_slug': 'solutions'},
            }},
        }
        return json.dumps(event, separators=(',', ':')).encode()

    def _signature(self, payload):
        digest = hmac.new(
            self.secret.encode(),
            b'1000.' + payload,
            hashlib.sha256,
        ).hexdigest()
        return f't=1000,v1={digest}'

    def test_maintenance_mode_blocks_provider_writes_but_not_reads(self):
        provider = FakeProvider()
        with mock.patch.dict(
            os.environ,
            {'MADMALLARD_BILLING_MAINTENANCE': 'true'},
            clear=False,
        ):
            with self.assertRaises(
                billing_provider.BillingProviderUnavailable
            ):
                billing_provider.execute(
                    provider,
                    billing_provider.ProviderRequest(
                        'customer.create',
                        {'email': 'owner@example.com'},
                    ),
                )
            self.assertEqual([], provider.calls)

    def test_rejected_webhook_can_be_retried_after_local_recovery(self):
        payload = self._payload()
        signature = self._signature(payload)
        with self.assertRaises(PermissionError):
            billing_operations.retry_rejected_stripe_event(
                payload, signature, self.secret, now=1000
            )

        provider = FakeProvider()
        billing_checkout.create_checkout_session(
            self.owner,
            'solutions',
            provider=provider,
            plan_slug='starter',
            customer_email='owner@example.com',
            customer_name='Example LLC',
            success_url='https://billing.example.com/success',
            cancel_url='https://billing.example.com/cancel',
            allowed_return_hosts={'billing.example.com'},
        )
        result = billing_operations.retry_rejected_stripe_event(
            payload, signature, self.secret, now=1000
        )
        self.assertEqual('processed', result.status)
        self.assertFalse(result.duplicate)

    def test_retry_rejects_event_identity_changes(self):
        payload = self._payload()
        signature = self._signature(payload)
        with self.assertRaises(PermissionError):
            billing_operations.retry_rejected_stripe_event(
                payload, signature, self.secret, now=1000
            )
        changed = self._payload(object_ref='cs_changed')
        with self.assertRaises(PermissionError):
            billing_operations.retry_rejected_stripe_event(
                changed,
                self._signature(changed),
                self.secret,
                now=1000,
            )

    def test_operational_summary_is_owner_admin_only_and_content_free(self):
        payload = self._payload()
        with self.assertRaises(PermissionError):
            billing_operations.retry_rejected_stripe_event(
                payload, self._signature(payload), self.secret, now=1000
            )
        summary = billing_operations.operational_summary(
            self.owner, 'solutions'
        )
        self.assertEqual('solutions', summary.organization_slug)
        self.assertNotIn('rejected', summary.provider_events_by_status)
        self.assertEqual((), summary.rejected_event_refs)

        with self.assertRaises(PermissionError):
            billing_operations.operational_summary(
                self.staff, 'solutions'
            )


if __name__ == '__main__':
    unittest.main()
