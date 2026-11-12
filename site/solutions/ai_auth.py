from __future__ import annotations

from dataclasses import dataclass

import ai_boundary
import tenant_sites


READ_ROLES = {'owner', 'admin', 'staff', 'viewer'}
USE_ROLES = {'owner', 'admin', 'staff'}
ADMIN_ROLES = {'owner', 'admin'}

CAPABILITIES = {
    'view_status': READ_ROLES,
    'draft': USE_ROLES,
    'summary': USE_ROLES,
    'suggested_reply': USE_ROLES,
    'knowledge_search': USE_ROLES,
    'view_usage': ADMIN_ROLES,
    'manage_settings': ADMIN_ROLES,
}


@dataclass(frozen=True)
class AIAccess:
    user_id: int
    organization_id: int
    organization_slug: str
    role: str
    site_slug: str | None
    can_use: bool
    can_administer: bool


def access_for(
    user_id: int,
    organization_slug: str,
    *,
    site_slug: str | None = None,
) -> AIAccess | None:
    try:
        scope = ai_boundary.authorize_request(
            user_id,
            organization_slug,
            site_slug=site_slug,
        )
    except (PermissionError, TypeError, ValueError):
        return None

    return AIAccess(
        user_id=scope.user_id,
        organization_id=scope.organization_id,
        organization_slug=scope.organization_slug,
        role=scope.role,
        site_slug=scope.site_slug,
        can_use=scope.role in USE_ROLES,
        can_administer=scope.role in ADMIN_ROLES,
    )


def can(
    user_id: int,
    organization_slug: str,
    capability: str,
    *,
    site_slug: str | None = None,
) -> bool:
    allowed = CAPABILITIES.get((capability or '').strip().lower())
    if not allowed:
        return False
    access = access_for(
        user_id,
        organization_slug,
        site_slug=site_slug,
    )
    return bool(access and access.role in allowed)


def require(
    user_id: int,
    organization_slug: str,
    capability: str,
    *,
    site_slug: str | None = None,
) -> AIAccess:
    access = access_for(
        user_id,
        organization_slug,
        site_slug=site_slug,
    )
    allowed = CAPABILITIES.get((capability or '').strip().lower())
    if not access or not allowed or access.role not in allowed:
        raise PermissionError('AI capability access denied.')
    return access


def require_site_resource(
    user_id: int,
    organization_slug: str,
    site_slug: str,
    capability: str,
) -> AIAccess:
    site = tenant_sites.get_site(organization_slug, site_slug)
    if site is None or site.status == 'archived':
        raise PermissionError('AI site capability access denied.')
    return require(
        user_id,
        organization_slug,
        capability,
        site_slug=site_slug,
    )
