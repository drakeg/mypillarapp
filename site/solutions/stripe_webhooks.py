from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import time

import billing_checkout
import billing_invoices
import billing_plans
import billing_subscriptions
import tenant_auth


SIGNATURE_TOLERANCE_SECONDS = 300
SUPPORTED_CHECKOUT_EVENT = 'checkout.session.completed'
SUPPORTED_SUBSCRIPTION_EVENTS = {
    'customer.subscription.created',
    'customer.subscription.updated',
    'customer.subscription.deleted',
}
SUPPORTED_INVOICE_EVENTS = {
    'invoice.created',
    'invoice.finalized',
    'invoice.paid',
    'invoice.payment_failed',
    'invoice.voided',
    'invoice.marked_uncollectible',
}
_STRIPE_STATUS_MAP = {
    'trialing': 'trialing',
    'active': 'active',
    'past_due': 'past_due',
    'unpaid': 'past_due',
    'incomplete': 'suspended',
    'incomplete_expired': 'canceled',
    'paused': 'suspended',
    'canceled': 'canceled',
}
_ALLOWED_TRANSITIONS = {
    'trialing': {'active', 'canceled', 'suspended'},
    'active': {'past_due', 'canceled', 'suspended'},
    'past_due': {'active', 'canceled', 'suspended'},
    'suspended': {'active', 'canceled'},
    'canceled': set(),
}


@dataclass(frozen=True)
class WebhookResult:
    event_ref: str
    event_type: str
    status: str
    organization_slug: str | None
    duplicate: bool
    detail: str


def ensure_schema() -> None:
    billing_checkout.ensure_schema()
    billing_subscriptions.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS billing_provider_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_name TEXT NOT NULL,
                event_ref TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_created INTEGER NOT NULL,
                organization_id INTEGER,
                object_ref TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                received_at INTEGER NOT NULL,
                UNIQUE(provider_name, event_ref),
                CHECK(status IN (
                    'received','processed','ignored','rejected'
                )),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE SET NULL
            )
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_billing_provider_events_org
            ON billing_provider_events(
                organization_id,provider_name,event_created,id
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS billing_subscription_provider_state (
                subscription_id INTEGER NOT NULL,
                provider_name TEXT NOT NULL,
                latest_event_created INTEGER NOT NULL,
                latest_event_ref TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY(subscription_id, provider_name),
                FOREIGN KEY(subscription_id)
                    REFERENCES billing_subscriptions(id) ON DELETE CASCADE
            )
            '''
        )
        conn.commit()


def verify_stripe_signature(
    payload: bytes,
    signature_header: str,
    webhook_secret: str,
    *,
    now: int | None = None,
    tolerance_seconds: int = SIGNATURE_TOLERANCE_SECONDS,
) -> int:
    if not isinstance(payload, (bytes, bytearray)):
        raise ValueError('Stripe webhook payload must be bytes.')
    secret = (webhook_secret or '').strip()
    if not secret:
        raise PermissionError('Stripe webhook secret is not configured.')
    timestamp, signatures = _parse_signature_header(signature_header)
    current = int(time.time()) if now is None else int(now)
    if abs(current - timestamp) > int(tolerance_seconds):
        raise PermissionError('Stripe webhook signature timestamp is stale.')

    signed = str(timestamp).encode('ascii') + b'.' + bytes(payload)
    expected = hmac.new(
        secret.encode('utf-8'),
        signed,
        hashlib.sha256,
    ).hexdigest()
    if not any(
        hmac.compare_digest(expected, signature)
        for signature in signatures
    ):
        raise PermissionError('Stripe webhook signature is invalid.')
    return timestamp


def process_stripe_event(
    payload: bytes,
    signature_header: str,
    webhook_secret: str,
    *,
    now: int | None = None,
    retry_rejected: bool = False,
) -> WebhookResult:
    verify_stripe_signature(
        payload,
        signature_header,
        webhook_secret,
        now=now,
    )
    event = _parse_event(payload)
    ensure_schema()

    event_ref = event['id']
    event_type = event['type']
    event_created = event['created']
    obj = event['data']['object']
    object_ref = str(obj.get('id') or '').strip()
    received_at = tenant_auth.now()

    with tenant_auth.db() as conn:
        existing = conn.execute(
            '''
            SELECT e.*,o.slug AS organization_slug
            FROM billing_provider_events e
            LEFT JOIN auth_organizations o ON o.id=e.organization_id
            WHERE e.provider_name='stripe' AND e.event_ref=?
            LIMIT 1
            ''',
            (event_ref,),
        ).fetchone()
        if existing is not None:
            if not (retry_rejected and str(existing['status']) == 'rejected'):
                return WebhookResult(
                    event_ref=event_ref,
                    event_type=event_type,
                    status=str(existing['status']),
                    organization_slug=(
                        str(existing['organization_slug'])
                        if existing['organization_slug'] is not None
                        else None
                    ),
                    duplicate=True,
                    detail=str(existing['detail']),
                )
            if (
                str(existing['event_type']) != event_type
                or int(existing['event_created']) != int(event_created)
                or str(existing['object_ref']) != object_ref
            ):
                raise PermissionError(
                    'Rejected Stripe event retry does not match the original event.'
                )
            conn.execute(
                '''UPDATE billing_provider_events
                   SET status='received',detail='',received_at=?
                   WHERE provider_name='stripe' AND event_ref=?''',
                (received_at, event_ref),
            )
            conn.commit()
        else:
        if existing is None:
            conn.execute(
            '''
            INSERT INTO billing_provider_events(
                provider_name,event_ref,event_type,event_created,
                organization_id,object_ref,status,detail,received_at
            ) VALUES('stripe',?,?,?,?,?,'received','',?)
            ''',
            (
                event_ref,
                event_type,
                event_created,
                None,
                object_ref,
                received_at,
            ),
        )
            conn.commit()

    try:
        if event_type == SUPPORTED_CHECKOUT_EVENT:
            return _process_checkout_completed(
                event_ref,
                event_type,
                event_created,
                obj,
            )
        if event_type in SUPPORTED_SUBSCRIPTION_EVENTS:
            return _process_subscription_event(
                event_ref,
                event_type,
                event_created,
                obj,
            )
        if event_type in SUPPORTED_INVOICE_EVENTS:
            organization_id, detail = billing_invoices.reconcile_stripe_invoice(
                event_ref=event_ref,
                event_type=event_type,
                event_created=event_created,
                invoice=obj,
            )
            return _finish_event(
                event_ref,
                status='processed',
                organization_id=organization_id,
                detail=detail,
            )
        if event_type.startswith('invoice.'):
            return _finish_event(
                event_ref,
                status='ignored',
                detail='unsupported_invoice_event',
            )
        return _finish_event(
            event_ref,
            status='ignored',
            detail='unsupported_event_type',
        )
    except Exception as exc:
        _finish_event(
            event_ref,
            status='rejected',
            detail=_safe_detail(exc),
        )
        raise


def _process_checkout_completed(
    event_ref: str,
    event_type: str,
    event_created: int,
    obj: dict[str, object],
) -> WebhookResult:
    session_ref = str(obj.get('id') or '').strip()
    if not session_ref:
        raise ValueError('Stripe checkout event is missing a session id.')

    with tenant_auth.db() as conn:
        rows = conn.execute(
            '''
            SELECT cs.*,o.slug AS organization_slug,p.slug AS plan_slug
            FROM billing_checkout_sessions cs
            JOIN auth_organizations o ON o.id=cs.organization_id
            JOIN billing_plans p
              ON p.id=cs.plan_id AND p.organization_id=cs.organization_id
            WHERE cs.provider_name='stripe' AND cs.session_ref=?
            ''',
            (session_ref,),
        ).fetchall()
        if len(rows) != 1:
            raise PermissionError(
                'Stripe checkout session does not resolve to one tenant.'
            )
        checkout = rows[0]

    org_slug = str(checkout['organization_slug'])
    _validate_metadata_tenant(obj, org_slug)

    customer_ref = str(obj.get('customer') or '').strip()
    if customer_ref and customer_ref != str(checkout['customer_ref']):
        raise PermissionError('Stripe checkout customer does not match tenant.')

    subscription_ref = str(obj.get('subscription') or '').strip()
    if not subscription_ref:
        raise ValueError(
            'Stripe checkout completion is missing a subscription reference.'
        )

    with tenant_auth.db() as conn:
        current = conn.execute(
            '''
            SELECT * FROM billing_subscriptions
            WHERE organization_id=? AND status!='canceled'
            ORDER BY id DESC LIMIT 1
            ''',
            (int(checkout['organization_id']),),
        ).fetchone()

        if current is not None:
            current_ref = str(current['provider_subscription_ref'] or '')
            if current_ref != subscription_ref:
                raise PermissionError(
                    'Tenant already has a different current subscription.'
                )
            if str(checkout['status']) != 'completed':
                conn.execute(
                    '''
                    UPDATE billing_checkout_sessions
                    SET status='completed'
                    WHERE id=? AND organization_id=?
                    ''',
                    (
                        int(checkout['id']),
                        int(checkout['organization_id']),
                    ),
                )
                conn.commit()
            _record_provider_state(
                conn,
                int(current['id']),
                event_created,
                event_ref,
            )
            conn.commit()
            return _finish_event(
                event_ref,
                status='processed',
                organization_id=int(checkout['organization_id']),
                detail='checkout_already_reconciled',
            )

        now = tenant_auth.now()
        conn.execute(
            '''
            UPDATE billing_checkout_sessions
            SET status='completed'
            WHERE id=? AND organization_id=?
            ''',
            (
                int(checkout['id']),
                int(checkout['organization_id']),
            ),
        )
        conn.execute(
            '''
            INSERT INTO billing_tenant_plans(
                organization_id,plan_id,assigned_by_user_id,assigned_at
            ) VALUES(?,?,?,?)
            ON CONFLICT(organization_id) DO UPDATE SET
                plan_id=excluded.plan_id,
                assigned_by_user_id=excluded.assigned_by_user_id,
                assigned_at=excluded.assigned_at
            ''',
            (
                int(checkout['organization_id']),
                int(checkout['plan_id']),
                int(checkout['created_by_user_id']),
                now,
            ),
        )
        cur = conn.execute(
            '''
            INSERT INTO billing_subscriptions(
                organization_id,plan_id,status,
                provider_customer_ref,provider_subscription_ref,
                created_at,updated_at,canceled_at
            ) VALUES(?,?, 'active', ?, ?, ?, ?, NULL)
            ''',
            (
                int(checkout['organization_id']),
                int(checkout['plan_id']),
                str(checkout['customer_ref']),
                subscription_ref,
                now,
                now,
            ),
        )
        subscription_id = int(cur.lastrowid)
        conn.execute(
            '''
            INSERT INTO billing_subscription_transitions(
                subscription_id,organization_id,from_status,to_status,
                actor_user_id,reason,created_at
            ) VALUES(?,?, 'active','active',?,?,?)
            ''',
            (
                subscription_id,
                int(checkout['organization_id']),
                int(checkout['created_by_user_id']),
                f'stripe_webhook_reconciled:{event_ref}',
                now,
            ),
        )
        _record_provider_state(
            conn,
            subscription_id,
            event_created,
            event_ref,
        )
        conn.commit()

    return _finish_event(
        event_ref,
        status='processed',
        organization_id=int(checkout['organization_id']),
        detail='checkout_reconciled',
    )


def _process_subscription_event(
    event_ref: str,
    event_type: str,
    event_created: int,
    obj: dict[str, object],
) -> WebhookResult:
    subscription_ref = str(obj.get('id') or '').strip()
    if not subscription_ref:
        raise ValueError(
            'Stripe subscription event is missing a subscription id.'
        )

    with tenant_auth.db() as conn:
        rows = conn.execute(
            '''
            SELECT s.*,o.slug AS organization_slug
            FROM billing_subscriptions s
            JOIN auth_organizations o ON o.id=s.organization_id
            WHERE s.provider_subscription_ref=?
            ''',
            (subscription_ref,),
        ).fetchall()
        if len(rows) != 1:
            raise PermissionError(
                'Stripe subscription does not resolve to one tenant.'
            )
        subscription = rows[0]

    org_slug = str(subscription['organization_slug'])
    _validate_metadata_tenant(obj, org_slug)

    customer_ref = str(obj.get('customer') or '').strip()
    expected_customer = str(subscription['provider_customer_ref'] or '')
    if customer_ref and expected_customer and customer_ref != expected_customer:
        raise PermissionError(
            'Stripe subscription customer does not match tenant.'
        )

    with tenant_auth.db() as conn:
        state = conn.execute(
            '''
            SELECT * FROM billing_subscription_provider_state
            WHERE subscription_id=? AND provider_name='stripe'
            LIMIT 1
            ''',
            (int(subscription['id']),),
        ).fetchone()
        if (
            state is not None
            and event_created <= int(state['latest_event_created'])
        ):
            return _finish_event(
                event_ref,
                status='ignored',
                organization_id=int(subscription['organization_id']),
                detail='stale_or_out_of_order_event',
            )

        target = _subscription_target_status(event_type, obj)
        current = str(subscription['status'])
        if target != current:
            if target not in _ALLOWED_TRANSITIONS.get(current, set()):
                raise ValueError(
                    f'Invalid provider subscription transition: '
                    f'{current} -> {target}.'
                )
            canceled_at = (
                tenant_auth.now() if target == 'canceled' else None
            )
            conn.execute(
                '''
                UPDATE billing_subscriptions
                SET status=?,updated_at=?,canceled_at=?
                WHERE id=? AND organization_id=?
                ''',
                (
                    target,
                    tenant_auth.now(),
                    canceled_at,
                    int(subscription['id']),
                    int(subscription['organization_id']),
                ),
            )

        _record_provider_state(
            conn,
            int(subscription['id']),
            event_created,
            event_ref,
        )
        conn.commit()

    return _finish_event(
        event_ref,
        status='processed',
        organization_id=int(subscription['organization_id']),
        detail=f'subscription_status:{target}',
    )


def _subscription_target_status(
    event_type: str,
    obj: dict[str, object],
) -> str:
    if event_type == 'customer.subscription.deleted':
        return 'canceled'
    raw = str(obj.get('status') or '').strip().lower()
    target = _STRIPE_STATUS_MAP.get(raw)
    if target is None:
        raise ValueError('Unsupported Stripe subscription status.')
    return target


def _record_provider_state(
    conn,
    subscription_id: int,
    event_created: int,
    event_ref: str,
) -> None:
    conn.execute(
        '''
        INSERT INTO billing_subscription_provider_state(
            subscription_id,provider_name,latest_event_created,
            latest_event_ref,updated_at
        ) VALUES(?,'stripe',?,?,?)
        ON CONFLICT(subscription_id,provider_name) DO UPDATE SET
            latest_event_created=excluded.latest_event_created,
            latest_event_ref=excluded.latest_event_ref,
            updated_at=excluded.updated_at
        ''',
        (
            subscription_id,
            event_created,
            event_ref,
            tenant_auth.now(),
        ),
    )


def _finish_event(
    event_ref: str,
    *,
    status: str,
    detail: str,
    organization_id: int | None = None,
) -> WebhookResult:
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            UPDATE billing_provider_events
            SET status=?,detail=?,organization_id=COALESCE(?,organization_id)
            WHERE provider_name='stripe' AND event_ref=?
            ''',
            (status, detail, organization_id, event_ref),
        )
        row = conn.execute(
            '''
            SELECT e.*,o.slug AS organization_slug
            FROM billing_provider_events e
            LEFT JOIN auth_organizations o ON o.id=e.organization_id
            WHERE e.provider_name='stripe' AND e.event_ref=?
            LIMIT 1
            ''',
            (event_ref,),
        ).fetchone()
        conn.commit()
    return WebhookResult(
        event_ref=event_ref,
        event_type=str(row['event_type']),
        status=str(row['status']),
        organization_slug=(
            str(row['organization_slug'])
            if row['organization_slug'] is not None
            else None
        ),
        duplicate=False,
        detail=str(row['detail']),
    )


def _validate_metadata_tenant(
    obj: dict[str, object],
    expected_slug: str,
) -> None:
    metadata = obj.get('metadata')
    if not isinstance(metadata, dict):
        return
    supplied = str(metadata.get('organization_slug') or '').strip().lower()
    if supplied and supplied != expected_slug:
        raise PermissionError(
            'Stripe metadata tenant does not match local ownership.'
        )


def _parse_signature_header(value: str) -> tuple[int, list[str]]:
    timestamp: int | None = None
    signatures: list[str] = []
    for part in (value or '').split(','):
        key, sep, raw = part.strip().partition('=')
        if not sep:
            continue
        if key == 't':
            try:
                timestamp = int(raw)
            except ValueError as exc:
                raise PermissionError(
                    'Stripe webhook signature timestamp is invalid.'
                ) from exc
        elif key == 'v1' and raw:
            signatures.append(raw)
    if timestamp is None or not signatures:
        raise PermissionError('Stripe webhook signature header is invalid.')
    return timestamp, signatures


def _parse_event(payload: bytes) -> dict[str, object]:
    try:
        event = json.loads(bytes(payload).decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('Stripe webhook payload is invalid JSON.') from exc
    if not isinstance(event, dict):
        raise ValueError('Stripe webhook event must be an object.')
    event_ref = str(event.get('id') or '').strip()
    event_type = str(event.get('type') or '').strip()
    created = event.get('created')
    data = event.get('data')
    if (
        not event_ref
        or not event_type
        or isinstance(created, bool)
        or not isinstance(created, int)
        or not isinstance(data, dict)
        or not isinstance(data.get('object'), dict)
    ):
        raise ValueError('Stripe webhook event is incomplete.')
    return event


def _safe_detail(exc: Exception) -> str:
    if isinstance(exc, PermissionError):
        return 'authorization_rejected'
    if isinstance(exc, ValueError):
        return 'validation_rejected'
    return 'processing_rejected'
