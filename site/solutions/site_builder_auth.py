from __future__ import annotations

from dataclasses import dataclass

import tenant_memberships
import tenant_sites


FULL_ADMIN_ROLES = {'owner', 'admin'}
CONTENT_ADMIN_ROLES = {'owner', 'admin', 'staff'}
CAPABILITIES = {
    'site_settings': FULL_ADMIN_ROLES,
    'domains': FULL_ADMIN_ROLES,
    'branding': CONTENT_ADMIN_ROLES,
    'navigation': CONTENT_ADMIN_ROLES,
    'pages': CONTENT_ADMIN_ROLES,
    'services': CONTENT_ADMIN_ROLES,
    'forms': CONTENT_ADMIN_ROLES,
    'media': CONTENT_ADMIN_ROLES,
}


@dataclass(frozen=True)
class SiteBuilderAccess:
    user_id: int
    organization_slug: str
    role: str
    can_full_admin: bool
    can_content_admin: bool


def access_for(user_id: int, organization_slug: str) -> SiteBuilderAccess | None:
    membership = tenant_memberships.get_membership(user_id, organization_slug)
    if not membership or membership.status != 'active':
        return None
    if membership.role not in FULL_ADMIN_ROLES | {'staff'}:
        return None
    return SiteBuilderAccess(
        user_id=user_id,
        organization_slug=membership.organization_slug,
        role=membership.role,
        can_full_admin=membership.role in FULL_ADMIN_ROLES,
        can_content_admin=membership.role in CONTENT_ADMIN_ROLES,
    )


def can_manage(user_id: int, organization_slug: str, capability: str) -> bool:
    allowed = CAPABILITIES.get((capability or '').strip().lower())
    if not allowed:
        return False
    membership = tenant_memberships.get_membership(user_id, organization_slug)
    return bool(
        membership
        and membership.status == 'active'
        and membership.role in allowed
    )


def can_manage_site(
    user_id: int,
    organization_slug: str,
    site_slug: str,
    capability: str,
) -> bool:
    site = tenant_sites.get_site(organization_slug, site_slug)
    return bool(
        site
        and site.status != 'archived'
        and can_manage(user_id, organization_slug, capability)
    )


def require_site_access(
    user_id: int,
    organization_slug: str,
    site_slug: str,
    capability: str,
) -> None:
    if not can_manage_site(user_id, organization_slug, site_slug, capability):
        raise PermissionError('Site Builder access denied.')
