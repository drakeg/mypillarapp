from __future__ import annotations

from dataclasses import dataclass

import billing_boundary
import billing_invoices
import billing_provider
import stripe_webhooks
import tenant_auth


@dataclass(frozen=True)
class BillingOperationsSummary:
    organization_slug: str
    maintenance_enabled: bool
    provider_events_by_status: dict[str, int]
    subscriptions_by_status: dict[str, int]
    invoices_by_status: dict[str, int]
    rejected_event_refs: tuple[str, ...]


def operational_summary(
    user_id: int,
    organization_slug: str,
    *,
    rejected_limit: int = 20,
) -> BillingOperationsSummary:
    scope = billing_boundary.authorize_billing_admin(
        user_id, organization_slug
    )
    limit = _bounded_limit(rejected_limit)
    stripe_webhooks.ensure_schema()
    billing_invoices.ensure_schema()

    with tenant_auth.db() as conn:
        provider_rows = conn.execute(
            '''
            SELECT status,COUNT(*) AS total
            FROM billing_provider_events
            WHERE organization_id=?
            GROUP BY status
            ORDER BY status
            ''',
            (scope.organization_id,),
        ).fetchall()
        subscription_rows = conn.execute(
            '''
            SELECT status,COUNT(*) AS total
            FROM billing_subscriptions
            WHERE organization_id=?
            GROUP BY status
            ORDER BY status
            ''',
            (scope.organization_id,),
        ).fetchall()
        invoice_rows = conn.execute(
            '''
            SELECT status,COUNT(*) AS total
            FROM billing_invoices
            WHERE organization_id=?
            GROUP BY status
            ORDER BY status
            ''',
            (scope.organization_id,),
        ).fetchall()
        rejected = conn.execute(
            '''
            SELECT event_ref
            FROM billing_provider_events
            WHERE organization_id=? AND status='rejected'
            ORDER BY received_at DESC,id DESC
            LIMIT ?
            ''',
            (scope.organization_id, limit),
        ).fetchall()

    return BillingOperationsSummary(
        organization_slug=scope.organization_slug,
        maintenance_enabled=billing_provider.maintenance_enabled(),
        provider_events_by_status={
            str(row['status']): int(row['total'])
            for row in provider_rows
        },
        subscriptions_by_status={
            str(row['status']): int(row['total'])
            for row in subscription_rows
        },
        invoices_by_status={
            str(row['status']): int(row['total'])
            for row in invoice_rows
        },
        rejected_event_refs=tuple(
            str(row['event_ref']) for row in rejected
        ),
    )


def retry_rejected_stripe_event(
    payload: bytes,
    signature_header: str,
    webhook_secret: str,
    *,
    now: int | None = None,
) -> stripe_webhooks.WebhookResult:
    return stripe_webhooks.process_stripe_event(
        payload,
        signature_header,
        webhook_secret,
        now=now,
        retry_rejected=True,
    )


def _bounded_limit(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError('Rejected-event limit must be an integer.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            'Rejected-event limit must be an integer.'
        ) from exc
    if clean < 1:
        raise ValueError('Rejected-event limit must be at least 1.')
    return min(clean, 100)
