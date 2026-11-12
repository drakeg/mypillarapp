from __future__ import annotations

from dataclasses import dataclass

import ai_boundary
import tenant_auth


DEFAULT_MAX_INPUT_UNITS = 4000
DEFAULT_MAX_OUTPUT_UNITS = 1000
DEFAULT_ROLLING_LIMIT_UNITS = 50000
MAX_INPUT_UNITS = 50000
MAX_OUTPUT_UNITS = 10000
MAX_ROLLING_LIMIT_UNITS = 5_000_000


@dataclass(frozen=True)
class AISettings:
    organization_id: int
    organization_slug: str
    enabled: bool
    max_input_units: int
    max_output_units: int
    rolling_limit_units: int
    updated_at: int


def ensure_schema() -> None:
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS ai_tenant_settings (
                organization_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0,
                max_input_units INTEGER NOT NULL,
                max_output_units INTEGER NOT NULL,
                rolling_limit_units INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                CHECK(enabled IN (0,1)),
                CHECK(max_input_units > 0),
                CHECK(max_output_units > 0),
                CHECK(rolling_limit_units > 0),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE
            )
            '''
        )
        conn.commit()


def get_settings(organization_slug: str) -> AISettings:
    slug = (organization_slug or '').strip().lower()
    ensure_schema()
    with tenant_auth.db() as conn:
        org = conn.execute(
            'SELECT id FROM auth_organizations WHERE slug=? LIMIT 1',
            (slug,),
        ).fetchone()
        if org is None:
            raise ValueError('Organization not found.')
        row = conn.execute(
            'SELECT * FROM ai_tenant_settings WHERE organization_id=?',
            (org['id'],),
        ).fetchone()
    if row is None:
        return AISettings(
            organization_id=int(org['id']),
            organization_slug=slug,
            enabled=False,
            max_input_units=DEFAULT_MAX_INPUT_UNITS,
            max_output_units=DEFAULT_MAX_OUTPUT_UNITS,
            rolling_limit_units=DEFAULT_ROLLING_LIMIT_UNITS,
            updated_at=0,
        )
    return AISettings(
        organization_id=int(row['organization_id']),
        organization_slug=slug,
        enabled=bool(row['enabled']),
        max_input_units=int(row['max_input_units']),
        max_output_units=int(row['max_output_units']),
        rolling_limit_units=int(row['rolling_limit_units']),
        updated_at=int(row['updated_at']),
    )


def update_settings(
    user_id: int,
    organization_slug: str,
    *,
    enabled: bool,
    max_input_units: int = DEFAULT_MAX_INPUT_UNITS,
    max_output_units: int = DEFAULT_MAX_OUTPUT_UNITS,
    rolling_limit_units: int = DEFAULT_ROLLING_LIMIT_UNITS,
) -> AISettings:
    scope = ai_boundary.authorize_request(user_id, organization_slug)
    if scope.role not in {'owner', 'admin'}:
        raise PermissionError('AI settings administration denied.')

    max_input_units = _bounded_positive(
        max_input_units, 'AI input limit', MAX_INPUT_UNITS
    )
    max_output_units = _bounded_positive(
        max_output_units, 'AI output limit', MAX_OUTPUT_UNITS
    )
    rolling_limit_units = _bounded_positive(
        rolling_limit_units, 'AI rolling limit', MAX_ROLLING_LIMIT_UNITS
    )

    ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            INSERT INTO ai_tenant_settings(
                organization_id, enabled, max_input_units,
                max_output_units, rolling_limit_units, updated_at
            ) VALUES(?,?,?,?,?,?)
            ON CONFLICT(organization_id) DO UPDATE SET
                enabled=excluded.enabled,
                max_input_units=excluded.max_input_units,
                max_output_units=excluded.max_output_units,
                rolling_limit_units=excluded.rolling_limit_units,
                updated_at=excluded.updated_at
            ''',
            (
                scope.organization_id,
                1 if bool(enabled) else 0,
                max_input_units,
                max_output_units,
                rolling_limit_units,
                tenant_auth.now(),
            ),
        )
        conn.commit()
    return get_settings(scope.organization_slug)


def require_usage_allowed(
    user_id: int,
    organization_slug: str,
    *,
    requested_input_units: int,
    requested_output_units: int,
    rolling_used_units: int = 0,
):
    scope = ai_boundary.authorize_request(user_id, organization_slug)
    settings = get_settings(scope.organization_slug)
    if not settings.enabled:
        raise PermissionError('AI is disabled for this organization.')

    input_units = _bounded_nonnegative(requested_input_units, 'AI input usage')
    output_units = _bounded_nonnegative(requested_output_units, 'AI output usage')
    rolling_used = _bounded_nonnegative(rolling_used_units, 'AI rolling usage')

    if input_units > settings.max_input_units:
        raise PermissionError('AI input limit exceeded.')
    if output_units > settings.max_output_units:
        raise PermissionError('AI output limit exceeded.')
    if rolling_used + input_units + output_units > settings.rolling_limit_units:
        raise PermissionError('AI rolling usage limit exceeded.')

    return scope, settings


def _bounded_positive(value: int, label: str, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f'{label} must be an integer.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label} must be an integer.') from exc
    if clean <= 0 or clean > maximum:
        raise ValueError(f'{label} must be between 1 and {maximum}.')
    return clean


def _bounded_nonnegative(value: int, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f'{label} must be an integer.')
    try:
        clean = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label} must be an integer.') from exc
    if clean < 0:
        raise ValueError(f'{label} cannot be negative.')
    return clean
