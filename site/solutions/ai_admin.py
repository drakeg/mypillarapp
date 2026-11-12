from __future__ import annotations

from dataclasses import dataclass

import ai_auth
import ai_execution
import ai_settings


@dataclass(frozen=True)
class AIStatus:
    organization_slug: str
    role: str
    enabled: bool
    max_input_units: int
    max_output_units: int
    rolling_limit_units: int
    rolling_used_units: int
    can_use: bool
    can_administer: bool


def status_for(
    user_id: int,
    organization_slug: str,
) -> AIStatus:
    access = ai_auth.require(
        user_id,
        organization_slug,
        'view_status',
    )
    settings = ai_settings.get_settings(access.organization_slug)
    rolling_used = ai_execution.rolling_usage_units(
        access.organization_slug
    )
    return AIStatus(
        organization_slug=access.organization_slug,
        role=access.role,
        enabled=settings.enabled,
        max_input_units=settings.max_input_units,
        max_output_units=settings.max_output_units,
        rolling_limit_units=settings.rolling_limit_units,
        rolling_used_units=rolling_used,
        can_use=access.can_use,
        can_administer=access.can_administer,
    )


def update_settings(
    user_id: int,
    organization_slug: str,
    *,
    enabled: bool,
    max_input_units: int = ai_settings.DEFAULT_MAX_INPUT_UNITS,
    max_output_units: int = ai_settings.DEFAULT_MAX_OUTPUT_UNITS,
    rolling_limit_units: int = ai_settings.DEFAULT_ROLLING_LIMIT_UNITS,
):
    ai_auth.require(
        user_id,
        organization_slug,
        'manage_settings',
    )
    return ai_settings.update_settings(
        user_id,
        organization_slug,
        enabled=enabled,
        max_input_units=max_input_units,
        max_output_units=max_output_units,
        rolling_limit_units=rolling_limit_units,
    )


def usage_records(
    user_id: int,
    organization_slug: str,
    *,
    limit: int = 100,
):
    ai_auth.require(
        user_id,
        organization_slug,
        'view_usage',
    )
    return ai_execution.list_usage(
        user_id,
        organization_slug,
        limit=limit,
    )
