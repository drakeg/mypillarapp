from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest import mock

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import billing_provider
import stripe_provider


class FakeTransport:
    def __init__(self, response=None, error=None):
        self.response = response or {
            'id': 'cus_123',
            'object': 'customer',
        }
        self.error = error
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return dict(self.response)


class Sprint8StripeProviderBoundaryTests(unittest.TestCase):
    def config(self):
        return stripe_provider.StripeConfig(
            secret_key='sk_test_example',
            webhook_secret='whsec_example',
        )

    def test_environment_configuration_is_required_and_not_persisted(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(billing_provider.BillingProviderError):
                stripe_provider.load_config_from_environment()

        with mock.patch.dict(
            os.environ,
            {
                'STRIPE_SECRET_KEY': 'sk_test_env',
                'STRIPE_WEBHOOK_SECRET': 'whsec_env',
            },
            clear=True,
        ):
            config = stripe_provider.load_config_from_environment(
                require_webhook_secret=True
            )
        self.assertEqual('sk_test_env', config.secret_key)
        self.assertEqual('whsec_env', config.webhook_secret)

    def test_provider_uses_narrow_injected_transport(self):
        transport = FakeTransport()
        provider = stripe_provider.StripeBillingProvider(
            self.config(), transport=transport
        )
        response = billing_provider.execute(
            provider,
            billing_provider.ProviderRequest(
                'customer.create',
                {
                    'email': 'owner@example.com',
                    'name': 'Example LLC',
                    'metadata': {'organization_slug': 'solutions'},
                },
            ),
        )
        self.assertEqual('stripe', response.provider_name)
        self.assertEqual('cus_123', response.object_id)
        self.assertEqual(1, len(transport.calls))
        call = transport.calls[0]
        self.assertEqual('POST', call['method'])
        self.assertTrue(call['url'].endswith('/v1/customers'))
        self.assertEqual(
            'Bearer sk_test_example',
            call['headers']['Authorization'],
        )

    def test_raw_payment_fields_are_rejected_before_transport(self):
        transport = FakeTransport()
        provider = stripe_provider.StripeBillingProvider(
            self.config(), transport=transport
        )
        for fields in (
            {'card_number': '4242424242424242'},
            {'card': {'number': '4242424242424242'}},
            {'payment_method_data': {'type': 'card'}},
            {'source': 'tok_example'},
        ):
            with self.assertRaises(ValueError):
                billing_provider.execute(
                    provider,
                    billing_provider.ProviderRequest(
                        'customer.create', fields
                    ),
                )
        self.assertEqual([], transport.calls)

    def test_provider_timeout_and_os_errors_are_controlled(self):
        class TimeoutProvider:
            provider_name = 'fake'
            def execute(self, request):
                raise TimeoutError('network detail')

        class OSProvider:
            provider_name = 'fake'
            def execute(self, request):
                raise OSError('socket detail')

        req = billing_provider.ProviderRequest(
            'customer.create', {'email': 'owner@example.com'}
        )
        with self.assertRaises(billing_provider.BillingProviderUnavailable):
            billing_provider.execute(TimeoutProvider(), req)
        with self.assertRaises(billing_provider.BillingProviderUnavailable):
            billing_provider.execute(OSProvider(), req)

    def test_incomplete_stripe_response_fails_closed(self):
        transport = FakeTransport(response={'object': 'customer'})
        provider = stripe_provider.StripeBillingProvider(
            self.config(), transport=transport
        )
        with self.assertRaises(billing_provider.BillingProviderError):
            billing_provider.execute(
                provider,
                billing_provider.ProviderRequest(
                    'customer.create',
                    {'email': 'owner@example.com'},
                ),
            )

    def test_retrieve_operations_accept_only_bounded_provider_id(self):
        transport = FakeTransport(
            response={
                'id': 'sub_123',
                'object': 'subscription',
                'status': 'active',
            }
        )
        provider = stripe_provider.StripeBillingProvider(
            self.config(), transport=transport
        )
        response = billing_provider.execute(
            provider,
            billing_provider.ProviderRequest(
                'subscription.retrieve',
                {'id': 'sub_123'},
            ),
        )
        self.assertEqual('sub_123', response.object_id)
        self.assertTrue(
            transport.calls[0]['url'].endswith('/v1/subscriptions/sub_123')
        )

    def test_http_api_base_must_be_https(self):
        with self.assertRaises(billing_provider.BillingProviderError):
            stripe_provider.validate_config(
                stripe_provider.StripeConfig(
                    secret_key='sk_test_example',
                    webhook_secret='',
                    api_base='http://api.stripe.com',
                )
            )


if __name__ == '__main__':
    unittest.main()
