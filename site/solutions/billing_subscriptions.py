from __future__ import annotations

from dataclasses import dataclass

import billing_boundary
import billing_plans
import tenant_auth


SUBSCRIPTION_STATUSES = {
    'trialing',
    'active',
    'past_due',
    'canceled',
    'suspended',
}
INITIAL_STATUSES = {'trialing', 'active'}
_ALLOWED_TRANSITIONS = {
    'trialing': {'active', 'canceled', 'suspended'},
    'active': {'past_due', 'canceled', 'suspended'},
    'past_due': {'active', 'canceled', 'suspended'},
    'suspended': {'active', 'canceled'},
    'canceled': set(),
}
MAX_REASON_LENGTH = 500


@dataclass(frozen=True)
class BillingSubscription:
    id: int
    organization_id: int
    organization_slug: str
    plan_id: int
    plan_slug: str
    status: str
    provider_customer_ref: str
    provider_subscription_ref: str
    created_at: int
    updated_at: int
    canceled_at: int | None


@dataclass(frozen=True)
class SubscriptionTransition:
    id: int
    subscription_id: int
    organization_id: int
    organization_slug: str
    from_status: str
    to_status: str
    actor_user_id: int
    reason: str
    created_at: int


def ensure_schema() -> None:
    billing_plans.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS billing_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                plan_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                provider_customer_ref TEXT NOT NULL DEFAULT '',
                provider_subscription_ref TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                canceled_at INTEGER,
                CHECK(status IN (
                    'trialing','active','past_due','canceled','suspended'
                )),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(plan_id)
                    REFERENCES billing_plans(id) ON DELETE RESTRICT
            )
            '''
        )
        conn.execute(
            '''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_billing_subscription_current_org
            ON billing_subscriptions(organization_id)
            WHERE status!='canceled'
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS billing_subscription_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id INTEGER NOT NULL,
                organization_id INTEGER NOT NULL,
                from_status TEXT NOT NULL,
                to_status TEXT NOT NULL,
                actor_user_id INTEGER NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                CHECK(from_status IN (
                    'trialing','active','past_due','canceled','suspended'
                )),
                CHECK(to_status IN (
                    'trialing','active','past_due','canceled','suspended'
                )),
                FOREIGN KEY(subscription_id)
                    REFERENCES billing_subscriptions(id) ON DELETE CASCADE,
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(actor_user_id)
                    REFERENCES auth_users(id) ON DELETE RESTRICT
            )
            '''
        )
        conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_billing_subscription_transitions
            ON billing_subscription_transitions(
                organization_id,subscription_id,created_at,id
            )
            '''
        )
        conn.commit()


def create_subscription(
    user_id: int,
    organization_slug: str,
    *,
    plan_slug: str,
    status: str = 'trialing',
    provider_customer_ref: str = '',
    provider_subscription_ref: str = '',
) -> BillingSubscription:
    scope = billing_boundary.authorize_billing_admin(
        user_id, organization_slug
    )
    clean_status = _status(status)
    if clean_status not in INITIAL_STATUSES:
        raise ValueError(
            'New subscriptions must start as trialing or active.'
        )
    plan = billing_plans.get_plan(scope.organization_slug, plan_slug)
    if plan is None or plan.status != 'active':
        raise ValueError('Active same-tenant billing plan not found.')

    customer_ref = _optional_provider_ref(
        provider_customer_ref, 'provider customer reference'
    )
    subscription_ref = _optional_provider_ref(
        provider_subscription_ref, 'provider subscription reference'
    )
    ensure_schema()
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        existing = conn.execute(
            '''
            SELECT id FROM billing_subscriptions
            WHERE organization_id=? AND status!='canceled'
            LIMIT 1
            ''',
            (scope.organization_id,),
        ).fetchone()
        if existing:
            raise ValueError(
                'Organization already has a current billing subscription.'
            )
        cur = conn.execute(
            '''
            INSERT INTO billing_subscriptions(
                organization_id,plan_id,status,
                provider_customer_ref,provider_subscription_ref,
                created_at,updated_at,canceled_at
            ) VALUES(?,?,?,?,?,?,?,NULL)
            ''',
            (
                scope.organization_id,
                plan.id,
                clean_status,
                customer_ref,
                subscription_ref,
                now,
                now,
            ),
        )
        conn.execute(
            '''
            INSERT INTO billing_subscription_transitions(
                subscription_id,organization_id,from_status,to_status,
                actor_user_id,reason,created_at
            ) VALUES(?,?,?, ?,?,?,?)
            ''',
            (
                int(cur.lastrowid),
                scope.organization_id,
                clean_status,
                clean_status,
                scope.user_id,
                'subscription_created',
                now,
            ),
        )
        conn.commit()
        row = _select_subscription(
            conn, scope.organization_id, int(cur.lastrowid)
        )
    return _subscription_from_row(row)


def get_subscription(
    organization_slug: str,
    subscription_id: int,
) -> BillingSubscription | None:
    ensure_schema()
    org_id = _organization_id(organization_slug)
    if org_id is None:
        return None
    with tenant_auth.db() as conn:
        row = _select_subscription(
            conn, org_id, _positive_int(subscription_id)
        )
    return _subscription_from_row(row) if row else None


def current_subscription(
    organization_slug: str,
) -> BillingSubscription | None:
    ensure_schema()
    org_id = _organization_id(organization_slug)
    if org_id is None:
        return None
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''
            SELECT s.*,o.slug AS organization_slug,p.slug AS plan_slug
            FROM billing_subscriptions s
            JOIN auth_organizations o ON o.id=s.organization_id
            JOIN billing_plans p ON p.id=s.plan_id
            WHERE s.organization_id=? AND s.status!='canceled'
            ORDER BY s.id DESC
            LIMIT 1
            ''',
            (org_id,),
        ).fetchone()
    return _subscription_from_row(row) if row else None


def list_subscriptions(
    organization_slug: str,
) -> list[BillingSubscription]:
    ensure_schema()
    org_id = _organization_id(organization_slug)
    if org_id is None:
        return []
    with tenant_auth.db() as conn:
        rows = conn.execute(
            '''
            SELECT s.*,o.slug AS organization_slug,p.slug AS plan_slug
            FROM billing_subscriptions s
            JOIN auth_organizations o ON o.id=s.organization_id
            JOIN billing_plans p ON p.id=s.plan_id
            WHERE s.organization_id=?
            ORDER BY s.created_at DESC,s.id DESC
            ''',
            (org_id,),
        ).fetchall()
    return [_subscription_from_row(row) for row in rows]


def transition_subscription(
    user_id: int,
    organization_slug: str,
    subscription_id: int,
    to_status: str,
    *,
    reason: str = '',
) -> BillingSubscription:
    scope = billing_boundary.authorize_billing_admin(
        user_id, organization_slug
    )
    target = _status(to_status)
    clean_reason = _reason(reason)
    ensure_schema()
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        row = _select_subscription(
            conn, scope.organization_id, _positive_int(subscription_id)
        )
        if row is None:
            raise ValueError(
                'Subscription is missing or belongs to another organization.'
            )
        current = str(row['status'])
        if target == current:
            raise ValueError('Subscription is already in that status.')
        if target not in _ALLOWED_TRANSITIONS[current]:
            raise ValueError(
                f'Invalid subscription transition: {current} -> {target}.'
            )

        canceled_at = now if target == 'canceled' else None
        conn.execute(
            '''
            UPDATE billing_subscriptions
            SET status=?,updated_at=?,canceled_at=?
            WHERE id=? AND organization_id=?
            ''',
            (
                target,
                now,
                canceled_at,
                int(subscription_id),
                scope.organization_id,
            ),
        )
        conn.execute(
            '''
            INSERT INTO billing_subscription_transitions(
                subscription_id,organization_id,from_status,to_status,
                actor_user_id,reason,created_at
            ) VALUES(?,?,?,?,?,?,?)
            ''',
            (
                int(subscription_id),
                scope.organization_id,
                current,
                target,
                scope.user_id,
                clean_reason,
                now,
            ),
        )
        conn.commit()
        updated = _select_subscription(
            conn, scope.organization_id, int(subscription_id)
        )
    return _subscription_from_row(updated)


def list_transitions(
    organization_slug: str,
    subscription_id: int,
) -> list[SubscriptionTransition]:
    ensure_schema()
    org_id = _organization_id(organization_slug)
    if org_id is None:
        return []
    sub_id = _positive_int(subscription_id)
    with tenant_auth.db() as conn:
        exists = _select_subscription(conn, org_id, sub_id)
        if exists is None:
            return []
        rows = conn.execute(
            '''
            SELECT t.*,o.slug AS organization_slug
            FROM billing_subscription_transitions t
            JOIN auth_organizations o ON o.id=t.organization_id
            WHERE t.organization_id=? AND t.subscription_id=?
            ORDER BY t.created_at,t.id
            ''',
            (org_id, sub_id),
        ).fetchall()
    return [_transition_from_row(row) for row in rows]


def _select_subscription(conn, organization_id: int, subscription_id: int):
    return conn.execute(
        '''
        SELECT s.*,o.slug AS organization_slug,p.slug AS plan_slug
        FROM billing_subscriptions s
        JOIN auth_organizations o ON o.id=s.organization_id
        JOIN billing_plans p
          ON p.id=s.plan_id AND p.organization_id=s.organization_id
        WHERE s.organization_id=? AND s.id=?
        LIMIT 1
        ''',
        (organization_id, subscription_id),
    ).fetchone()


def _organization_id(organization_slug: str) -> int | None:
    slug = (organization_slug or '').strip().lower()
    with tenant_auth.db() as conn:
        row = conn.execute(
            'SELECT id FROM auth_organizations WHERE slug=? LIMIT 1',
            (slug,),
        ).fetchone()
    return int(row['id']) if row else None


def _optional_provider_ref(value: str, label: str) -> str:
    clean = (value or '').strip()
    if not clean:
        return ''
    return billing_boundary.validate_provider_reference(
        clean, label=label
    )


def _status(value: str) -> str:
    clean = (value or '').strip().lower()
    if clean not in SUBSCRIPTION_STATUSES:
        raise ValueError(f'Unknown subscription status: {clean}')
    return clean


def _reason(value: str) -> str:
    clean = (value or '').strip()
    if len(clean) > MAX_REASON_LENGTH:
        raise ValueError(
            f'Subscription transition reason must be {MAX_REASON_LENGTH} '
            'characters or fewer.'
        )
    return clean


def _positive_int(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError('Subscription identifier must be a positive integer.')
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            'Subscription identifier must be a positive integer.'
        ) from exc
    if parsed <= 0:
        raise ValueError(
            'Subscription identifier must be a positive integer.'
        )
    return parsed


def _subscription_from_row(row) -> BillingSubscription:
    return BillingSubscription(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        plan_id=int(row['plan_id']),
        plan_slug=str(row['plan_slug']),
        status=str(row['status']),
        provider_customer_ref=str(row['provider_customer_ref']),
        provider_subscription_ref=str(row['provider_subscription_ref']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
        canceled_at=(
            int(row['canceled_at'])
            if row['canceled_at'] is not None
            else None
        ),
    )


def _transition_from_row(row) -> SubscriptionTransition:
    return SubscriptionTransition(
        id=int(row['id']),
        subscription_id=int(row['subscription_id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        from_status=str(row['from_status']),
        to_status=str(row['to_status']),
        actor_user_id=int(row['actor_user_id']),
        reason=str(row['reason']),
        created_at=int(row['created_at']),
    )
