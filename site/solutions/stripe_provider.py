from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Mapping, Protocol
from urllib import error, parse, request

import billing_boundary
import billing_provider


DEFAULT_API_BASE = 'https://api.stripe.com'
DEFAULT_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class StripeConfig:
    secret_key: str
    webhook_secret: str
    api_base: str = DEFAULT_API_BASE
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS


class StripeTransport(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        fields: Mapping[str, object],
        timeout_seconds: int,
    ) -> dict[str, object]:
        ...


class UrllibStripeTransport:
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        fields: Mapping[str, object],
        timeout_seconds: int,
    ) -> dict[str, object]:
        data = None
        if fields:
            flattened = _flatten_form(fields)
            data = parse.urlencode(flattened, doseq=True).encode('utf-8')
        req = request.Request(
            url,
            data=data,
            method=method,
            headers=dict(headers),
        )
        try:
            with request.urlopen(req, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except error.HTTPError as exc:
            raise billing_provider.BillingProviderError(
                f'Stripe request failed with HTTP {exc.code}.'
            ) from exc
        except error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise billing_provider.BillingProviderUnavailable(
                    'Stripe request timed out.'
                ) from exc
            raise billing_provider.BillingProviderUnavailable(
                'Stripe request unavailable.'
            ) from exc
        except (TimeoutError, OSError) as exc:
            raise billing_provider.BillingProviderUnavailable(
                'Stripe request unavailable.'
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise billing_provider.BillingProviderError(
                'Stripe returned an invalid response.'
            ) from exc

        if not isinstance(payload, dict):
            raise billing_provider.BillingProviderError(
                'Stripe returned an invalid response.'
            )
        return payload


class StripeBillingProvider:
    provider_name = 'stripe'

    def __init__(
        self,
        config: StripeConfig,
        *,
        transport: StripeTransport | None = None,
    ):
        self.config = validate_config(config)
        self.transport = transport or UrllibStripeTransport()

    def execute(
        self,
        request_data: billing_provider.ProviderRequest,
    ) -> billing_provider.ProviderResponse:
        checked = billing_provider.validate_request(request_data)
        method, path, fields = _operation_request(checked)
        payload = self.transport.request(
            method=method,
            url=self.config.api_base + path,
            headers={
                'Authorization': f'Bearer {self.config.secret_key}',
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'MadMallardPlatform/1',
            },
            fields=fields,
            timeout_seconds=self.config.timeout_seconds,
        )
        object_id = str(payload.get('id') or '').strip()
        object_type = str(payload.get('object') or '').strip()
        raw_status = str(payload.get('status') or '').strip()
        if not object_id or not object_type:
            raise billing_provider.BillingProviderError(
                'Stripe returned an incomplete object.'
            )
        return billing_provider.ProviderResponse(
            provider_name=self.provider_name,
            operation=checked.operation,
            object_id=billing_boundary.validate_provider_reference(
                object_id, label='Stripe object reference'
            ),
            object_type=object_type,
            raw_status=raw_status,
        )


def load_config_from_environment(
    *,
    require_webhook_secret: bool = False,
) -> StripeConfig:
    secret_key = (os.environ.get('STRIPE_SECRET_KEY') or '').strip()
    webhook_secret = (os.environ.get('STRIPE_WEBHOOK_SECRET') or '').strip()
    api_base = (os.environ.get('STRIPE_API_BASE') or DEFAULT_API_BASE).strip()
    timeout_raw = (
        os.environ.get('STRIPE_TIMEOUT_SECONDS')
        or str(DEFAULT_TIMEOUT_SECONDS)
    ).strip()

    if not secret_key:
        raise billing_provider.BillingProviderError(
            'Stripe secret key is not configured.'
        )
    if require_webhook_secret and not webhook_secret:
        raise billing_provider.BillingProviderError(
            'Stripe webhook secret is not configured.'
        )
    try:
        timeout_seconds = int(timeout_raw)
    except ValueError as exc:
        raise billing_provider.BillingProviderError(
            'Stripe timeout must be an integer.'
        ) from exc

    return validate_config(
        StripeConfig(
            secret_key=secret_key,
            webhook_secret=webhook_secret,
            api_base=api_base,
            timeout_seconds=timeout_seconds,
        )
    )


def validate_config(config: StripeConfig) -> StripeConfig:
    if not config.secret_key.strip():
        raise billing_provider.BillingProviderError(
            'Stripe secret key is not configured.'
        )
    if not config.api_base.startswith('https://'):
        raise billing_provider.BillingProviderError(
            'Stripe API base must use HTTPS.'
        )
    if config.timeout_seconds < 1 or config.timeout_seconds > 60:
        raise billing_provider.BillingProviderError(
            'Stripe timeout must be between 1 and 60 seconds.'
        )
    return StripeConfig(
        secret_key=config.secret_key.strip(),
        webhook_secret=config.webhook_secret.strip(),
        api_base=config.api_base.rstrip('/'),
        timeout_seconds=int(config.timeout_seconds),
    )


def _operation_request(
    provider_request: billing_provider.ProviderRequest,
) -> tuple[str, str, Mapping[str, object]]:
    fields = dict(provider_request.fields)
    operation = provider_request.operation
    if operation == 'customer.create':
        return 'POST', '/v1/customers', fields
    if operation == 'checkout_session.create':
        return 'POST', '/v1/checkout/sessions', fields
    if operation == 'subscription.retrieve':
        object_id = billing_boundary.validate_provider_reference(
            str(fields.pop('id', '')),
            label='Stripe subscription reference',
        )
        if fields:
            raise ValueError('Subscription retrieval accepts only an id.')
        return 'GET', f'/v1/subscriptions/{parse.quote(object_id, safe="")}', {}
    if operation == 'invoice.retrieve':
        object_id = billing_boundary.validate_provider_reference(
            str(fields.pop('id', '')),
            label='Stripe invoice reference',
        )
        if fields:
            raise ValueError('Invoice retrieval accepts only an id.')
        return 'GET', f'/v1/invoices/{parse.quote(object_id, safe="")}', {}
    raise ValueError(f'Unsupported Stripe operation: {operation}')


def _flatten_form(
    fields: Mapping[str, object],
    prefix: str = '',
) -> list[tuple[str, str]]:
    output: list[tuple[str, str]] = []
    for key, value in fields.items():
        name = f'{prefix}[{key}]' if prefix else str(key)
        if isinstance(value, Mapping):
            output.extend(_flatten_form(value, name))
        elif isinstance(value, (list, tuple)):
            for item in value:
                output.append((f'{name}[]', str(item)))
        elif value is not None:
            output.append((name, str(value)))
    return output
