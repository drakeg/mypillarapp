from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import urlsplit

import billing_boundary
import billing_plans
import billing_provider
import tenant_auth


MAX_EMAIL_LENGTH = 320
MAX_NAME_LENGTH = 160


@dataclass(frozen=True)
class ProviderCustomer:
    organization_id: int
    organization_slug: str
    provider_name: str
    customer_ref: str
    created_by_user_id: int
    created_at: int


@dataclass(frozen=True)
class PlanProviderPrice:
    organization_id: int
    organization_slug: str
    plan_id: int
    plan_slug: str
    provider_name: str
    price_ref: str
    configured_by_user_id: int
    configured_at: int


@dataclass(frozen=True)
class CheckoutSession:
    id: int
    organization_id: int
    organization_slug: str
    plan_id: int
    plan_slug: str
    provider_name: str
    customer_ref: str
    session_ref: str
    checkout_url: str
    status: str
    created_by_user_id: int
    created_at: int


def ensure_schema() -> None:
    billing_plans.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS billing_provider_customers (
                organization_id INTEGER NOT NULL,
                provider_name TEXT NOT NULL,
                customer_ref TEXT NOT NULL,
                created_by_user_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY(organization_id, provider_name),
                UNIQUE(provider_name, customer_ref),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(created_by_user_id)
                    REFERENCES auth_users(id) ON DELETE RESTRICT
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS billing_plan_provider_prices (
                organization_id INTEGER NOT NULL,
                plan_id INTEGER NOT NULL,
                provider_name TEXT NOT NULL,
                price_ref TEXT NOT NULL,
                configured_by_user_id INTEGER NOT NULL,
                configured_at INTEGER NOT NULL,
                PRIMARY KEY(organization_id, plan_id, provider_name),
                UNIQUE(provider_name, price_ref),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(plan_id)
                    REFERENCES billing_plans(id) ON DELETE CASCADE,
                FOREIGN KEY(configured_by_user_id)
                    REFERENCES auth_users(id) ON DELETE RESTRICT
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS billing_checkout_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                plan_id INTEGER NOT NULL,
                provider_name TEXT NOT NULL,
                customer_ref TEXT NOT NULL,
                session_ref TEXT NOT NULL,
                checkout_url TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_by_user_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                UNIQUE(provider_name, session_ref),
                CHECK(status IN ('pending','completed','expired','canceled')),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(plan_id)
                    REFERENCES billing_plans(id) ON DELETE RESTRICT,
                FOREIGN KEY(created_by_user_id)
                    REFERENCES auth_users(id) ON DELETE RESTRICT
            )
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_billing_checkout_org_created
            ON billing_checkout_sessions(organization_id,created_at,id)
            '''
        )
        conn.commit()


def configure_plan_price(
    user_id: int,
    organization_slug: str,
    *,
    plan_slug: str,
    provider_name: str,
    price_ref: str,
) -> PlanProviderPrice:
    scope = billing_boundary.authorize_billing_admin(
        user_id, organization_slug
    )
    provider = _provider_name(provider_name)
    price = billing_boundary.validate_provider_reference(
        price_ref, label='provider price reference'
    )
    plan = billing_plans.get_plan(scope.organization_slug, plan_slug)
    if plan is None or plan.status != 'active':
        raise ValueError('Active same-tenant billing plan not found.')

    ensure_schema()
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            INSERT INTO billing_plan_provider_prices(
                organization_id,plan_id,provider_name,price_ref,
                configured_by_user_id,configured_at
            ) VALUES(?,?,?,?,?,?)
            ON CONFLICT(organization_id,plan_id,provider_name) DO UPDATE SET
                price_ref=excluded.price_ref,
                configured_by_user_id=excluded.configured_by_user_id,
                configured_at=excluded.configured_at
            ''',
            (
                scope.organization_id,
                plan.id,
                provider,
                price,
                scope.user_id,
                now,
            ),
        )
        conn.commit()
    return get_plan_price(
        scope.organization_slug, plan.slug, provider
    )


def get_plan_price(
    organization_slug: str,
    plan_slug: str,
    provider_name: str,
) -> PlanProviderPrice | None:
    ensure_schema()
    provider = _provider_name(provider_name)
    plan = billing_plans.get_plan(organization_slug, plan_slug)
    if plan is None:
        return None
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''
            SELECT pp.*,o.slug AS organization_slug,p.slug AS plan_slug
            FROM billing_plan_provider_prices pp
            JOIN auth_organizations o ON o.id=pp.organization_id
            JOIN billing_plans p
              ON p.id=pp.plan_id AND p.organization_id=pp.organization_id
            WHERE pp.organization_id=?
              AND pp.plan_id=?
              AND pp.provider_name=?
            LIMIT 1
            ''',
            (plan.organization_id, plan.id, provider),
        ).fetchone()
    return _price_from_row(row) if row else None


def ensure_provider_customer(
    user_id: int,
    organization_slug: str,
    *,
    provider: billing_provider.BillingProvider,
    email: str,
    name: str,
) -> ProviderCustomer:
    scope = billing_boundary.authorize_billing_admin(
        user_id, organization_slug
    )
    ensure_schema()
    provider_name = _provider_name(provider.provider_name)

    existing = get_provider_customer(
        scope.organization_slug, provider_name
    )
    if existing is not None:
        return existing

    clean_email = _email(email)
    clean_name = _name(name)
    response = billing_provider.execute(
        provider,
        billing_provider.ProviderRequest(
            'customer.create',
            {
                'email': clean_email,
                'name': clean_name,
                'metadata': {
                    'organization_slug': scope.organization_slug,
                },
            },
        ),
    )
    if response.object_type != 'customer':
        raise billing_provider.BillingProviderError(
            'Billing provider returned the wrong object type.'
        )

    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            INSERT INTO billing_provider_customers(
                organization_id,provider_name,customer_ref,
                created_by_user_id,created_at
            ) VALUES(?,?,?,?,?)
            ''',
            (
                scope.organization_id,
                provider_name,
                response.object_id,
                scope.user_id,
                now,
            ),
        )
        conn.commit()
    return get_provider_customer(
        scope.organization_slug, provider_name
    )


def get_provider_customer(
    organization_slug: str,
    provider_name: str,
) -> ProviderCustomer | None:
    ensure_schema()
    provider = _provider_name(provider_name)
    slug = (organization_slug or '').strip().lower()
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''
            SELECT pc.*,o.slug AS organization_slug
            FROM billing_provider_customers pc
            JOIN auth_organizations o ON o.id=pc.organization_id
            WHERE o.slug=? AND pc.provider_name=?
            LIMIT 1
            ''',
            (slug, provider),
        ).fetchone()
    return _customer_from_row(row) if row else None


def create_checkout_session(
    user_id: int,
    organization_slug: str,
    *,
    provider: billing_provider.BillingProvider,
    plan_slug: str,
    customer_email: str,
    customer_name: str,
    success_url: str,
    cancel_url: str,
    allowed_return_hosts: set[str] | None = None,
) -> CheckoutSession:
    scope = billing_boundary.authorize_billing_admin(
        user_id, organization_slug
    )
    provider_name = _provider_name(provider.provider_name)
    plan = billing_plans.get_plan(scope.organization_slug, plan_slug)
    if plan is None or plan.status != 'active':
        raise ValueError('Active same-tenant billing plan not found.')

    price = get_plan_price(
        scope.organization_slug, plan.slug, provider_name
    )
    if price is None:
        raise ValueError(
            'Billing plan does not have a provider price mapping.'
        )

    hosts = (
        configured_return_hosts()
        if allowed_return_hosts is None
        else {_host(value) for value in allowed_return_hosts}
    )
    clean_success = validate_return_url(success_url, hosts)
    clean_cancel = validate_return_url(cancel_url, hosts)

    customer = ensure_provider_customer(
        scope.user_id,
        scope.organization_slug,
        provider=provider,
        email=customer_email,
        name=customer_name,
    )

    response = billing_provider.execute(
        provider,
        billing_provider.ProviderRequest(
            'checkout_session.create',
            {
                'mode': 'subscription',
                'customer': customer.customer_ref,
                'success_url': clean_success,
                'cancel_url': clean_cancel,
                'line_items': [
                    {
                        'price': price.price_ref,
                        'quantity': 1,
                    },
                ],
                'metadata': {
                    'organization_slug': scope.organization_slug,
                    'plan_slug': plan.slug,
                },
            },
        ),
    )
    if response.object_type != 'checkout.session':
        raise billing_provider.BillingProviderError(
            'Billing provider returned the wrong object type.'
        )
    checkout_url = validate_checkout_url(response.redirect_url)

    ensure_schema()
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        cur = conn.execute(
            '''
            INSERT INTO billing_checkout_sessions(
                organization_id,plan_id,provider_name,customer_ref,
                session_ref,checkout_url,status,created_by_user_id,created_at
            ) VALUES(?,?,?,?,?,?,'pending',?,?)
            ''',
            (
                scope.organization_id,
                plan.id,
                provider_name,
                customer.customer_ref,
                response.object_id,
                checkout_url,
                scope.user_id,
                now,
            ),
        )
        conn.commit()
        row = _select_checkout(
            conn, scope.organization_id, int(cur.lastrowid)
        )
    return _checkout_from_row(row)


def get_checkout_session(
    organization_slug: str,
    checkout_id: int,
) -> CheckoutSession | None:
    ensure_schema()
    slug = (organization_slug or '').strip().lower()
    with tenant_auth.db() as conn:
        org = conn.execute(
            'SELECT id FROM auth_organizations WHERE slug=? LIMIT 1',
            (slug,),
        ).fetchone()
        if org is None:
            return None
        row = _select_checkout(
            conn,
            int(org['id']),
            _positive_int(checkout_id),
        )
    return _checkout_from_row(row) if row else None


def configured_return_hosts() -> set[str]:
    raw = os.environ.get('MADMALLARD_BILLING_RETURN_HOSTS', '')
    hosts = {
        _host(value)
        for value in raw.split(',')
        if value.strip()
    }
    if not hosts:
        raise ValueError(
            'MADMALLARD_BILLING_RETURN_HOSTS is not configured.'
        )
    return hosts


def validate_return_url(value: str, allowed_hosts: set[str]) -> str:
    clean = (value or '').strip()
    parsed = urlsplit(clean)
    if parsed.scheme != 'https' or not parsed.hostname:
        raise ValueError('Billing return URL must use HTTPS.')
    if parsed.username or parsed.password:
        raise ValueError('Billing return URL must not include credentials.')
    host = parsed.hostname.lower()
    if host not in allowed_hosts:
        raise ValueError('Billing return URL host is not allow-listed.')
    return clean


def validate_checkout_url(value: str) -> str:
    clean = (value or '').strip()
    parsed = urlsplit(clean)
    if parsed.scheme != 'https' or not parsed.hostname:
        raise billing_provider.BillingProviderError(
            'Billing provider checkout URL must use HTTPS.'
        )
    if parsed.username or parsed.password:
        raise billing_provider.BillingProviderError(
            'Billing provider checkout URL is invalid.'
        )
    return clean


def _provider_name(value: str) -> str:
    clean = (value or '').strip().lower()
    if not clean or len(clean) > 40:
        raise ValueError('Billing provider name is invalid.')
    if not clean.replace('-', '').replace('_', '').isalnum():
        raise ValueError('Billing provider name is invalid.')
    return clean


def _host(value: str) -> str:
    clean = (value or '').strip().lower()
    if not clean or '/' in clean or ':' in clean:
        raise ValueError('Billing return host is invalid.')
    return clean


def _email(value: str) -> str:
    clean = (value or '').strip()
    if (
        not clean
        or len(clean) > MAX_EMAIL_LENGTH
        or '@' not in clean
        or clean.startswith('@')
        or clean.endswith('@')
    ):
        raise ValueError('Customer email is invalid.')
    return clean


def _name(value: str) -> str:
    clean = (value or '').strip()
    if not clean:
        raise ValueError('Customer name is required.')
    if len(clean) > MAX_NAME_LENGTH:
        raise ValueError(
            f'Customer name must be {MAX_NAME_LENGTH} characters or fewer.'
        )
    return clean


def _positive_int(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError('Checkout identifier must be a positive integer.')
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            'Checkout identifier must be a positive integer.'
        ) from exc
    if parsed <= 0:
        raise ValueError(
            'Checkout identifier must be a positive integer.'
        )
    return parsed


def _select_checkout(conn, organization_id: int, checkout_id: int):
    return conn.execute(
        '''
        SELECT cs.*,o.slug AS organization_slug,p.slug AS plan_slug
        FROM billing_checkout_sessions cs
        JOIN auth_organizations o ON o.id=cs.organization_id
        JOIN billing_plans p
          ON p.id=cs.plan_id AND p.organization_id=cs.organization_id
        WHERE cs.organization_id=? AND cs.id=?
        LIMIT 1
        ''',
        (organization_id, checkout_id),
    ).fetchone()


def _customer_from_row(row) -> ProviderCustomer:
    return ProviderCustomer(
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        provider_name=str(row['provider_name']),
        customer_ref=str(row['customer_ref']),
        created_by_user_id=int(row['created_by_user_id']),
        created_at=int(row['created_at']),
    )


def _price_from_row(row) -> PlanProviderPrice:
    return PlanProviderPrice(
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        plan_id=int(row['plan_id']),
        plan_slug=str(row['plan_slug']),
        provider_name=str(row['provider_name']),
        price_ref=str(row['price_ref']),
        configured_by_user_id=int(row['configured_by_user_id']),
        configured_at=int(row['configured_at']),
    )


def _checkout_from_row(row) -> CheckoutSession:
    return CheckoutSession(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        plan_id=int(row['plan_id']),
        plan_slug=str(row['plan_slug']),
        provider_name=str(row['provider_name']),
        customer_ref=str(row['customer_ref']),
        session_ref=str(row['session_ref']),
        checkout_url=str(row['checkout_url']),
        status=str(row['status']),
        created_by_user_id=int(row['created_by_user_id']),
        created_at=int(row['created_at']),
    )
