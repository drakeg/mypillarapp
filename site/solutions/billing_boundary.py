from __future__ import annotations

from dataclasses import dataclass

import creator_storefront
import crm_quotes
import tenant_auth
import tenant_memberships
import tenant_sites


BILLING_DATA_CLASSES = {
    'plan',
    'entitlement',
    'subscription',
    'invoice',
    'license',
    'provider_customer_ref',
    'provider_subscription_ref',
    'provider_invoice_ref',
    'provider_event_ref',
}

PROHIBITED_PAYMENT_DATA_CLASSES = {
    'card_number',
    'card_cvc',
    'card_cvv',
    'magstripe_data',
    'bank_account_number',
    'routing_number',
    'payment_provider_secret',
    'webhook_secret',
    'session_token',
    'raw_payment_method',
}

LEGACY_PRICE_SOURCES = {
    'crm_quote',
    'storefront_product',
    'site_service_price_text',
}

MAX_PROVIDER_REFERENCE_LENGTH = 255


@dataclass(frozen=True)
class BillingScope:
    user_id: int
    organization_id: int
    organization_slug: str
    role: str


@dataclass(frozen=True)
class LegacyPriceReference:
    source_class: str
    identifier: str
    site_slug: str | None = None


def classify_billing_data(data_class: str) -> str:
    normalized = (data_class or '').strip().lower()
    if normalized in BILLING_DATA_CLASSES:
        return 'eligible'
    if normalized in PROHIBITED_PAYMENT_DATA_CLASSES:
        return 'prohibited'
    return 'unknown'


def authorize_scope(user_id: int, organization_slug: str) -> BillingScope:
    slug = (organization_slug or '').strip().lower()
    try:
        user_id = int(user_id)
    except (TypeError, ValueError) as exc:
        raise PermissionError('Billing access denied.') from exc

    with tenant_auth.db() as conn:
        user = conn.execute(
            'SELECT id, is_active FROM auth_users WHERE id=? LIMIT 1',
            (user_id,),
        ).fetchone()
        organization = conn.execute(
            'SELECT id, status FROM auth_organizations WHERE slug=? LIMIT 1',
            (slug,),
        ).fetchone()

    if not user or int(user['is_active']) != 1:
        raise PermissionError('Billing access denied.')
    if not organization or organization['status'] != 'active':
        raise PermissionError('Billing access denied.')

    membership = tenant_memberships.get_membership(user_id, slug)
    if membership is None or membership.status != 'active':
        raise PermissionError('Billing access denied.')

    return BillingScope(
        user_id=user_id,
        organization_id=int(organization['id']),
        organization_slug=slug,
        role=membership.role,
    )


def authorize_billing_admin(user_id: int, organization_slug: str) -> BillingScope:
    scope = authorize_scope(user_id, organization_slug)
    if scope.role not in {'owner', 'admin'}:
        raise PermissionError('Billing administration denied.')
    return scope


def validate_provider_reference(value: str, *, label: str = 'provider reference') -> str:
    clean = (value or '').strip()
    if not clean:
        raise ValueError(f'{label.capitalize()} is required.')
    if len(clean) > MAX_PROVIDER_REFERENCE_LENGTH:
        raise ValueError(
            f'{label.capitalize()} must be {MAX_PROVIDER_REFERENCE_LENGTH} characters or fewer.'
        )
    if any(ord(char) < 32 for char in clean):
        raise ValueError(f'{label.capitalize()} contains invalid control characters.')
    return clean


def validate_legacy_price_reference(
    scope: BillingScope,
    reference: LegacyPriceReference,
) -> None:
    source_class = (reference.source_class or '').strip().lower()
    if source_class not in LEGACY_PRICE_SOURCES:
        raise PermissionError('Legacy price source is not eligible.')

    if source_class == 'crm_quote':
        quote = crm_quotes.get_quote(
            scope.organization_slug,
            _positive_int(reference.identifier),
        )
        if quote is None:
            raise PermissionError('Legacy quote reference denied.')
        return

    if source_class == 'storefront_product':
        site_slug = (reference.site_slug or '').strip().lower()
        if not site_slug:
            raise PermissionError('Storefront product requires an explicit site scope.')
        site = tenant_sites.get_site(scope.organization_slug, site_slug)
        if site is None or site.status == 'archived':
            raise PermissionError('Storefront product site denied.')
        product = creator_storefront.get_product(
            scope.organization_slug,
            site_slug,
            _positive_int(reference.identifier),
        )
        if product is None:
            raise PermissionError('Storefront product reference denied.')
        return

    if source_class == 'site_service_price_text':
        raise PermissionError(
            'Legacy service price text is presentation-only and cannot authorize billing.'
        )

    raise PermissionError('Legacy price reference denied.')


def legacy_price_can_authorize_charge(reference: LegacyPriceReference) -> bool:
    # Sprint 8 intentionally requires a later explicit billing record/migration.
    # Existing quotes, catalog prices, and service price text remain descriptive.
    return False


def provider_state_can_authorize_access() -> bool:
    # Provider/customer/subscription IDs and webhook state are reconciliation
    # inputs only. Deterministic application entitlements remain authoritative.
    return False


def _positive_int(value: str) -> int:
    if isinstance(value, bool):
        raise PermissionError('Billing reference denied.')
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PermissionError('Billing reference denied.') from exc
    if parsed <= 0:
        raise PermissionError('Billing reference denied.')
    return parsed
