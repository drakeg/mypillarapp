from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import billing_boundary
import billing_subscriptions
import tenant_auth


INVOICE_STATUSES = {
    'draft',
    'open',
    'paid',
    'void',
    'uncollectible',
}
MAX_INVOICE_READ_LIMIT = 100


@dataclass(frozen=True)
class BillingInvoice:
    id: int
    organization_id: int
    organization_slug: str
    subscription_id: int
    provider_name: str
    provider_invoice_ref: str
    provider_customer_ref: str
    provider_subscription_ref: str
    status: str
    currency: str
    amount_due: int
    amount_paid: int
    amount_remaining: int
    hosted_invoice_url: str
    invoice_pdf_url: str
    due_at: int | None
    paid_at: int | None
    latest_event_created: int
    latest_event_ref: str
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    billing_subscriptions.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS billing_invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                subscription_id INTEGER NOT NULL,
                provider_name TEXT NOT NULL,
                provider_invoice_ref TEXT NOT NULL,
                provider_customer_ref TEXT NOT NULL DEFAULT '',
                provider_subscription_ref TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                currency TEXT NOT NULL,
                amount_due INTEGER NOT NULL DEFAULT 0,
                amount_paid INTEGER NOT NULL DEFAULT 0,
                amount_remaining INTEGER NOT NULL DEFAULT 0,
                hosted_invoice_url TEXT NOT NULL DEFAULT '',
                invoice_pdf_url TEXT NOT NULL DEFAULT '',
                due_at INTEGER,
                paid_at INTEGER,
                latest_event_created INTEGER NOT NULL,
                latest_event_ref TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(provider_name, provider_invoice_ref),
                CHECK(status IN (
                    'draft','open','paid','void','uncollectible'
                )),
                CHECK(amount_due >= 0),
                CHECK(amount_paid >= 0),
                CHECK(amount_remaining >= 0),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(subscription_id)
                    REFERENCES billing_subscriptions(id) ON DELETE RESTRICT
            )
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_billing_invoices_org_created
            ON billing_invoices(
                organization_id,created_at DESC,id DESC
            )
            '''
        )
        conn.commit()


def reconcile_stripe_invoice(
    *,
    event_ref: str,
    event_type: str,
    event_created: int,
    invoice: dict[str, object],
) -> tuple[int, str]:
    ensure_schema()

    invoice_ref = billing_boundary.validate_provider_reference(
        str(invoice.get('id') or ''),
        label='Stripe invoice reference',
    )
    subscription_ref = _stripe_subscription_ref(invoice)
    if not subscription_ref:
        raise PermissionError(
            'Stripe invoice does not reference a local subscription.'
        )

    subscription = _subscription_by_provider_ref(subscription_ref)
    if subscription is None:
        raise PermissionError(
            'Stripe invoice subscription does not resolve to one tenant.'
        )

    customer_ref = str(invoice.get('customer') or '').strip()
    expected_customer = str(
        subscription['provider_customer_ref'] or ''
    ).strip()
    if (
        customer_ref
        and expected_customer
        and customer_ref != expected_customer
    ):
        raise PermissionError(
            'Stripe invoice customer does not match tenant.'
        )

    _validate_metadata_tenant(
        invoice,
        str(subscription['organization_slug']),
    )

    status = _invoice_status(event_type, invoice)
    currency = _currency(invoice.get('currency'))
    amount_due = _money(invoice.get('amount_due'))
    amount_paid = _money(invoice.get('amount_paid'))
    amount_remaining = _money(invoice.get('amount_remaining'))
    hosted_url = _https_reference(
        invoice.get('hosted_invoice_url'),
        'hosted invoice URL',
    )
    pdf_url = _https_reference(
        invoice.get('invoice_pdf'),
        'invoice PDF URL',
    )
    due_at = _optional_timestamp(invoice.get('due_date'))
    paid_at = _paid_at(invoice)

    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        existing = conn.execute(
            '''
            SELECT * FROM billing_invoices
            WHERE provider_name='stripe'
              AND provider_invoice_ref=?
            LIMIT 1
            ''',
            (invoice_ref,),
        ).fetchone()

        if (
            existing is not None
            and event_created <= int(existing['latest_event_created'])
        ):
            return (
                int(existing['organization_id']),
                'invoice_stale_or_out_of_order',
            )

        if existing is None:
            conn.execute(
                '''
                INSERT INTO billing_invoices(
                    organization_id,subscription_id,provider_name,
                    provider_invoice_ref,provider_customer_ref,
                    provider_subscription_ref,status,currency,
                    amount_due,amount_paid,amount_remaining,
                    hosted_invoice_url,invoice_pdf_url,due_at,paid_at,
                    latest_event_created,latest_event_ref,
                    created_at,updated_at
                ) VALUES(?,?,'stripe',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ''',
                (
                    int(subscription['organization_id']),
                    int(subscription['id']),
                    invoice_ref,
                    customer_ref,
                    subscription_ref,
                    status,
                    currency,
                    amount_due,
                    amount_paid,
                    amount_remaining,
                    hosted_url,
                    pdf_url,
                    due_at,
                    paid_at,
                    event_created,
                    event_ref,
                    now,
                    now,
                ),
            )
        else:
            if int(existing['organization_id']) != int(
                subscription['organization_id']
            ):
                raise PermissionError(
                    'Stripe invoice ownership changed across tenants.'
                )
            conn.execute(
                '''
                UPDATE billing_invoices
                SET subscription_id=?,
                    provider_customer_ref=?,
                    provider_subscription_ref=?,
                    status=?,
                    currency=?,
                    amount_due=?,
                    amount_paid=?,
                    amount_remaining=?,
                    hosted_invoice_url=?,
                    invoice_pdf_url=?,
                    due_at=?,
                    paid_at=?,
                    latest_event_created=?,
                    latest_event_ref=?,
                    updated_at=?
                WHERE id=? AND organization_id=?
                ''',
                (
                    int(subscription['id']),
                    customer_ref,
                    subscription_ref,
                    status,
                    currency,
                    amount_due,
                    amount_paid,
                    amount_remaining,
                    hosted_url,
                    pdf_url,
                    due_at,
                    paid_at,
                    event_created,
                    event_ref,
                    now,
                    int(existing['id']),
                    int(subscription['organization_id']),
                ),
            )
        conn.commit()

    return int(subscription['organization_id']), f'invoice_status:{status}'


def list_invoices(
    user_id: int,
    organization_slug: str,
    *,
    limit: int = 50,
) -> list[BillingInvoice]:
    scope = billing_boundary.authorize_billing_admin(
        user_id, organization_slug
    )
    bounded = _read_limit(limit)
    ensure_schema()
    with tenant_auth.db() as conn:
        rows = conn.execute(
            '''
            SELECT i.*,o.slug AS organization_slug
            FROM billing_invoices i
            JOIN auth_organizations o ON o.id=i.organization_id
            WHERE i.organization_id=?
            ORDER BY i.created_at DESC,i.id DESC
            LIMIT ?
            ''',
            (scope.organization_id, bounded),
        ).fetchall()
    return [_invoice_from_row(row) for row in rows]


def get_invoice(
    user_id: int,
    organization_slug: str,
    invoice_id: int,
) -> BillingInvoice | None:
    scope = billing_boundary.authorize_billing_admin(
        user_id, organization_slug
    )
    ensure_schema()
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''
            SELECT i.*,o.slug AS organization_slug
            FROM billing_invoices i
            JOIN auth_organizations o ON o.id=i.organization_id
            WHERE i.organization_id=? AND i.id=?
            LIMIT 1
            ''',
            (scope.organization_id, _positive_int(invoice_id)),
        ).fetchone()
    return _invoice_from_row(row) if row else None


def _subscription_by_provider_ref(provider_ref: str):
    with tenant_auth.db() as conn:
        rows = conn.execute(
            '''
            SELECT s.*,o.slug AS organization_slug
            FROM billing_subscriptions s
            JOIN auth_organizations o ON o.id=s.organization_id
            WHERE s.provider_subscription_ref=?
            ''',
            (provider_ref,),
        ).fetchall()
    if len(rows) != 1:
        return None
    return rows[0]


def _stripe_subscription_ref(invoice: dict[str, object]) -> str:
    direct = str(invoice.get('subscription') or '').strip()
    if direct:
        return direct

    parent = invoice.get('parent')
    if isinstance(parent, dict):
        details = parent.get('subscription_details')
        if isinstance(details, dict):
            nested = str(details.get('subscription') or '').strip()
            if nested:
                return nested
    return ''


def _invoice_status(
    event_type: str,
    invoice: dict[str, object],
) -> str:
    if event_type == 'invoice.paid':
        return 'paid'
    if event_type == 'invoice.voided':
        return 'void'
    if event_type == 'invoice.marked_uncollectible':
        return 'uncollectible'
    raw = str(invoice.get('status') or '').strip().lower()
    if raw not in INVOICE_STATUSES:
        raise ValueError('Unsupported Stripe invoice status.')
    return raw


def _currency(value: object) -> str:
    clean = str(value or '').strip().lower()
    if len(clean) != 3 or not clean.isalpha():
        raise ValueError('Invoice currency must be a 3-letter code.')
    return clean


def _money(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError('Invoice amount must be a non-negative integer.')
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            'Invoice amount must be a non-negative integer.'
        ) from exc
    if parsed < 0:
        raise ValueError(
            'Invoice amount must be a non-negative integer.'
        )
    return parsed


def _https_reference(value: object, label: str) -> str:
    clean = str(value or '').strip()
    if not clean:
        return ''
    parsed = urlsplit(clean)
    if (
        parsed.scheme != 'https'
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError(f'{label.capitalize()} must be a valid HTTPS URL.')
    return clean


def _optional_timestamp(value: object) -> int | None:
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        raise ValueError('Invoice timestamp must be a positive integer.')
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            'Invoice timestamp must be a positive integer.'
        ) from exc
    if parsed <= 0:
        raise ValueError('Invoice timestamp must be a positive integer.')
    return parsed


def _paid_at(invoice: dict[str, object]) -> int | None:
    transitions = invoice.get('status_transitions')
    if not isinstance(transitions, dict):
        return None
    return _optional_timestamp(transitions.get('paid_at'))


def _validate_metadata_tenant(
    invoice: dict[str, object],
    expected_slug: str,
) -> None:
    metadata = invoice.get('metadata')
    if not isinstance(metadata, dict):
        return
    supplied = str(
        metadata.get('organization_slug') or ''
    ).strip().lower()
    if supplied and supplied != expected_slug:
        raise PermissionError(
            'Stripe invoice metadata tenant does not match local ownership.'
        )


def _read_limit(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError('Invoice read limit must be an integer.')
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Invoice read limit must be an integer.') from exc
    if parsed < 1:
        raise ValueError('Invoice read limit must be at least 1.')
    return min(parsed, MAX_INVOICE_READ_LIMIT)


def _positive_int(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError('Invoice identifier must be a positive integer.')
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            'Invoice identifier must be a positive integer.'
        ) from exc
    if parsed <= 0:
        raise ValueError(
            'Invoice identifier must be a positive integer.'
        )
    return parsed


def _invoice_from_row(row) -> BillingInvoice:
    return BillingInvoice(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        subscription_id=int(row['subscription_id']),
        provider_name=str(row['provider_name']),
        provider_invoice_ref=str(row['provider_invoice_ref']),
        provider_customer_ref=str(row['provider_customer_ref']),
        provider_subscription_ref=str(
            row['provider_subscription_ref']
        ),
        status=str(row['status']),
        currency=str(row['currency']),
        amount_due=int(row['amount_due']),
        amount_paid=int(row['amount_paid']),
        amount_remaining=int(row['amount_remaining']),
        hosted_invoice_url=str(row['hosted_invoice_url']),
        invoice_pdf_url=str(row['invoice_pdf_url']),
        due_at=(
            int(row['due_at']) if row['due_at'] is not None else None
        ),
        paid_at=(
            int(row['paid_at']) if row['paid_at'] is not None else None
        ),
        latest_event_created=int(row['latest_event_created']),
        latest_event_ref=str(row['latest_event_ref']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
