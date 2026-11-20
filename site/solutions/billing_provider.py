from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping, Protocol


ALLOWED_OPERATIONS = {
    'customer.create',
    'checkout_session.create',
    'subscription.retrieve',
    'invoice.retrieve',
}
BILLING_MAINTENANCE_ENV = 'MADMALLARD_BILLING_MAINTENANCE'
WRITE_OPERATIONS = {'customer.create', 'checkout_session.create'}

PROHIBITED_FIELD_NAMES = {
    'api_key',
    'secret_key',
    'webhook_secret',
    'card_number',
    'card_cvc',
    'card_cvv',
    'bank_account_number',
    'routing_number',
    'raw_payment_method',
    'card',
    'number',
    'cvc',
    'cvv',
    'payment_method',
    'payment_method_data',
    'source',
}


class BillingProviderError(RuntimeError):
    pass


class BillingProviderUnavailable(BillingProviderError):
    pass


@dataclass(frozen=True)
class ProviderRequest:
    operation: str
    fields: Mapping[str, object]


@dataclass(frozen=True)
class ProviderResponse:
    provider_name: str
    operation: str
    object_id: str
    object_type: str
    raw_status: str
    redirect_url: str = ''


class BillingProvider(Protocol):
    provider_name: str

    def execute(self, request: ProviderRequest) -> ProviderResponse:
        ...


def validate_request(request: ProviderRequest) -> ProviderRequest:
    operation = (request.operation or '').strip().lower()
    if operation not in ALLOWED_OPERATIONS:
        raise ValueError(f'Unsupported billing provider operation: {operation}')
    if not isinstance(request.fields, Mapping):
        raise ValueError('Billing provider fields must be a mapping.')
    _reject_prohibited_fields(request.fields)
    return ProviderRequest(operation=operation, fields=request.fields)


def maintenance_enabled() -> bool:
    return os.environ.get(BILLING_MAINTENANCE_ENV, '').strip().lower() in {
        '1', 'true', 'yes', 'on',
    }


def execute(provider: BillingProvider, request: ProviderRequest) -> ProviderResponse:
    checked = validate_request(request)
    if maintenance_enabled() and checked.operation in WRITE_OPERATIONS:
        raise BillingProviderUnavailable(
            'Billing provider writes are temporarily disabled for maintenance.'
        )
    try:
        response = provider.execute(checked)
    except BillingProviderError:
        raise
    except TimeoutError as exc:
        raise BillingProviderUnavailable('Billing provider timed out.') from exc
    except OSError as exc:
        raise BillingProviderUnavailable('Billing provider unavailable.') from exc

    if not isinstance(response, ProviderResponse):
        raise BillingProviderError('Billing provider returned an invalid response.')
    if response.provider_name != provider.provider_name:
        raise BillingProviderError('Billing provider identity mismatch.')
    if response.operation != checked.operation:
        raise BillingProviderError('Billing provider operation mismatch.')
    if not response.object_id or not response.object_type:
        raise BillingProviderError('Billing provider response is incomplete.')
    return response


def _reject_prohibited_fields(value: object, *, path: str = '') -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            clean = str(key).strip().lower()
            if clean in PROHIBITED_FIELD_NAMES:
                raise ValueError(
                    f'Prohibited payment field in provider request: {path + clean}'
                )
            _reject_prohibited_fields(child, path=f'{path}{clean}.')
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_prohibited_fields(child, path=f'{path}{index}.')
