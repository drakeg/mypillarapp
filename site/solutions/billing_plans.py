from __future__ import annotations

from dataclasses import dataclass
import json
import re

import billing_boundary
import tenant_auth


PLAN_STATUSES = {'active', 'archived'}
ENTITLEMENT_KEYS = {
    'sites',
    'crm',
    'portal',
    'creator',
    'ai',
    'ai_rolling_units',
}
_BOOLEAN_KEYS = {'crm', 'portal', 'creator', 'ai'}
_QUOTA_KEYS = {'sites', 'ai_rolling_units'}
_SLUG_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
MAX_QUOTA = 10_000_000

# Existing/internal tenants remain usable until explicitly assigned a Sprint 8 plan.
# This is application policy, not provider state.
_INTERNAL_DEFAULTS: dict[str, bool | int | None] = {
    'sites': None,
    'crm': True,
    'portal': True,
    'creator': True,
    'ai': True,
    'ai_rolling_units': None,
}


@dataclass(frozen=True)
class BillingPlan:
    id: int
    slug: str
    name: str
    status: str
    commercial: bool
    entitlements: dict[str, bool | int | None]
    created_at: int
    updated_at: int


@dataclass(frozen=True)
class TenantPlanAssignment:
    organization_id: int
    organization_slug: str
    plan_id: int
    plan_slug: str
    assigned_by_user_id: int
    assigned_at: int


@dataclass(frozen=True)
class EntitlementDecision:
    organization_slug: str
    key: str
    allowed: bool
    quota: int | None
    source: str
    plan_slug: str | None


def ensure_schema() -> None:
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS billing_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                commercial INTEGER NOT NULL DEFAULT 1,
                entitlements_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                CHECK(status IN ('active','archived')),
                CHECK(commercial IN (0,1))
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS billing_tenant_plans (
                organization_id INTEGER PRIMARY KEY,
                plan_id INTEGER NOT NULL,
                assigned_by_user_id INTEGER NOT NULL,
                assigned_at INTEGER NOT NULL,
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(plan_id)
                    REFERENCES billing_plans(id) ON DELETE RESTRICT,
                FOREIGN KEY(assigned_by_user_id)
                    REFERENCES auth_users(id) ON DELETE RESTRICT
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_billing_plans_status_slug '
            'ON billing_plans(status, slug)'
        )
        conn.commit()


def create_plan(
    user_id: int,
    organization_slug: str,
    *,
    slug: str,
    name: str,
    entitlements: dict[str, object],
    commercial: bool = True,
) -> BillingPlan:
    billing_boundary.authorize_billing_admin(user_id, organization_slug)
    clean_slug = _plan_slug(slug)
    clean_name = _plan_name(name)
    clean_entitlements = _normalize_entitlements(entitlements)
    ensure_schema()
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        try:
            cur = conn.execute(
                '''
                INSERT INTO billing_plans(
                    slug,name,status,commercial,entitlements_json,
                    created_at,updated_at
                ) VALUES(?,?,'active',?,?,?,?)
                ''',
                (
                    clean_slug,
                    clean_name,
                    1 if bool(commercial) else 0,
                    json.dumps(clean_entitlements, sort_keys=True),
                    now,
                    now,
                ),
            )
        except Exception as exc:
            if 'UNIQUE constraint failed' in str(exc):
                raise ValueError('A billing plan with that slug already exists.') from exc
            raise
        conn.commit()
        row = conn.execute(
            'SELECT * FROM billing_plans WHERE id=?',
            (cur.lastrowid,),
        ).fetchone()
    return _plan_from_row(row)


def get_plan(slug: str) -> BillingPlan | None:
    ensure_schema()
    with tenant_auth.db() as conn:
        row = conn.execute(
            'SELECT * FROM billing_plans WHERE slug=? LIMIT 1',
            (_plan_slug(slug),),
        ).fetchone()
    return _plan_from_row(row) if row else None


def list_plans(*, include_archived: bool = False) -> list[BillingPlan]:
    ensure_schema()
    sql = 'SELECT * FROM billing_plans'
    if not include_archived:
        sql += " WHERE status='active'"
    sql += ' ORDER BY name COLLATE NOCASE, id'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql).fetchall()
    return [_plan_from_row(row) for row in rows]


def archive_plan(
    user_id: int,
    organization_slug: str,
    plan_slug: str,
) -> BillingPlan:
    billing_boundary.authorize_billing_admin(user_id, organization_slug)
    ensure_schema()
    clean_slug = _plan_slug(plan_slug)
    with tenant_auth.db() as conn:
        assigned = conn.execute(
            '''
            SELECT 1
            FROM billing_tenant_plans tp
            JOIN billing_plans p ON p.id=tp.plan_id
            WHERE p.slug=?
            LIMIT 1
            ''',
            (clean_slug,),
        ).fetchone()
        if assigned:
            raise ValueError('Assigned billing plans cannot be archived.')
        cur = conn.execute(
            "UPDATE billing_plans SET status='archived', updated_at=? "
            "WHERE slug=? AND status!='archived'",
            (tenant_auth.now(), clean_slug),
        )
        if cur.rowcount != 1:
            raise ValueError('Active billing plan not found.')
        conn.commit()
    return get_plan(clean_slug)


def assign_plan(
    user_id: int,
    organization_slug: str,
    plan_slug: str,
) -> TenantPlanAssignment:
    scope = billing_boundary.authorize_billing_admin(user_id, organization_slug)
    plan = get_plan(plan_slug)
    if plan is None or plan.status != 'active':
        raise ValueError('Active billing plan not found.')
    ensure_schema()
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
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
            (scope.organization_id, plan.id, scope.user_id, now),
        )
        conn.commit()
    return get_assignment(scope.organization_slug)


def get_assignment(organization_slug: str) -> TenantPlanAssignment | None:
    slug = (organization_slug or '').strip().lower()
    ensure_schema()
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''
            SELECT tp.*,o.slug AS organization_slug,p.slug AS plan_slug
            FROM billing_tenant_plans tp
            JOIN auth_organizations o ON o.id=tp.organization_id
            JOIN billing_plans p ON p.id=tp.plan_id
            WHERE o.slug=?
            LIMIT 1
            ''',
            (slug,),
        ).fetchone()
    if row is None:
        return None
    return TenantPlanAssignment(
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        plan_id=int(row['plan_id']),
        plan_slug=str(row['plan_slug']),
        assigned_by_user_id=int(row['assigned_by_user_id']),
        assigned_at=int(row['assigned_at']),
    )


def entitlement(
    organization_slug: str,
    key: str,
) -> EntitlementDecision:
    clean_key = _entitlement_key(key)
    assignment = get_assignment(organization_slug)
    if assignment is None:
        value = _INTERNAL_DEFAULTS[clean_key]
        return _decision(
            assignment.organization_slug if assignment else (organization_slug or '').strip().lower(),
            clean_key,
            value,
            source='internal_default',
            plan_slug=None,
        )

    plan = get_plan(assignment.plan_slug)
    if plan is None or plan.status != 'active':
        return EntitlementDecision(
            organization_slug=assignment.organization_slug,
            key=clean_key,
            allowed=False,
            quota=None,
            source='inactive_plan',
            plan_slug=assignment.plan_slug,
        )
    value = plan.entitlements.get(clean_key)
    return _decision(
        assignment.organization_slug,
        clean_key,
        value,
        source='plan',
        plan_slug=plan.slug,
    )


def require_entitlement(
    organization_slug: str,
    key: str,
    *,
    requested_units: int = 0,
) -> EntitlementDecision:
    decision = entitlement(organization_slug, key)
    if not decision.allowed:
        raise PermissionError(f'Entitlement denied: {decision.key}.')
    units = _nonnegative_int(requested_units, 'Requested entitlement units')
    if decision.quota is not None and units > decision.quota:
        raise PermissionError(f'Entitlement quota exceeded: {decision.key}.')
    return decision


def _decision(
    organization_slug: str,
    key: str,
    value: bool | int | None,
    *,
    source: str,
    plan_slug: str | None,
) -> EntitlementDecision:
    if key in _BOOLEAN_KEYS:
        allowed = value is True
        return EntitlementDecision(
            organization_slug=organization_slug,
            key=key,
            allowed=allowed,
            quota=None,
            source=source,
            plan_slug=plan_slug,
        )
    quota = value if isinstance(value, int) and not isinstance(value, bool) else None
    allowed = value is None or quota is not None
    return EntitlementDecision(
        organization_slug=organization_slug,
        key=key,
        allowed=allowed,
        quota=quota,
        source=source,
        plan_slug=plan_slug,
    )


def _normalize_entitlements(values: dict[str, object]) -> dict[str, bool | int | None]:
    if not isinstance(values, dict):
        raise ValueError('Plan entitlements must be a mapping.')
    unknown = set(values) - ENTITLEMENT_KEYS
    if unknown:
        raise ValueError(f'Unknown entitlement: {sorted(unknown)[0]}')
    normalized: dict[str, bool | int | None] = {}
    for key in ENTITLEMENT_KEYS:
        if key in _BOOLEAN_KEYS:
            value = values.get(key, False)
            if not isinstance(value, bool):
                raise ValueError(f'Entitlement {key} must be boolean.')
            normalized[key] = value
        else:
            value = values.get(key, 0)
            if value is None:
                normalized[key] = None
            else:
                normalized[key] = _nonnegative_int(value, f'Entitlement {key}')
                if normalized[key] > MAX_QUOTA:
                    raise ValueError(f'Entitlement {key} exceeds the maximum quota.')
    return normalized


def _entitlement_key(value: str) -> str:
    clean = (value or '').strip().lower()
    if clean not in ENTITLEMENT_KEYS:
        raise PermissionError('Unknown entitlement.')
    return clean


def _plan_slug(value: str) -> str:
    clean = (value or '').strip().lower()
    if not clean or not _SLUG_RE.fullmatch(clean):
        raise ValueError('Plan slug must use lowercase letters/numbers and hyphens.')
    if len(clean) > 80:
        raise ValueError('Plan slug must be 80 characters or fewer.')
    return clean


def _plan_name(value: str) -> str:
    clean = (value or '').strip()
    if not clean:
        raise ValueError('Plan name is required.')
    if len(clean) > 160:
        raise ValueError('Plan name must be 160 characters or fewer.')
    return clean


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f'{label} must be a non-negative integer.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label} must be a non-negative integer.') from exc
    if clean < 0:
        raise ValueError(f'{label} must be a non-negative integer.')
    return clean


def _plan_from_row(row) -> BillingPlan:
    return BillingPlan(
        id=int(row['id']),
        slug=str(row['slug']),
        name=str(row['name']),
        status=str(row['status']),
        commercial=bool(row['commercial']),
        entitlements=json.loads(row['entitlements_json']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
