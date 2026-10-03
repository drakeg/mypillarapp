from __future__ import annotations

from dataclasses import dataclass

import tenant_memberships


READ_ROLES = {'owner', 'admin', 'staff', 'viewer'}
WRITE_ROLES = {'owner', 'admin', 'staff'}
ADMIN_ROLES = {'owner', 'admin'}

CAPABILITIES = {
    'view': READ_ROLES,
    'companies': WRITE_ROLES,
    'contacts': WRITE_ROLES,
    'opportunities': WRITE_ROLES,
    'tasks': WRITE_ROLES,
    'activities': WRITE_ROLES,
    'conversation_links': WRITE_ROLES,
    'quotes': WRITE_ROLES,
    'crm_admin': ADMIN_ROLES,
}


@dataclass(frozen=True)
class CrmAccess:
    user_id: int
    organization_slug: str
    role: str
    can_view: bool
    can_manage: bool
    can_administer: bool


def access_for(user_id: int, organization_slug: str) -> CrmAccess | None:
    membership = tenant_memberships.get_membership(user_id, organization_slug)
    if not membership or membership.status != 'active':
        return None
    if membership.role not in READ_ROLES:
        return None
    return CrmAccess(
        user_id=user_id,
        organization_slug=membership.organization_slug,
        role=membership.role,
        can_view=True,
        can_manage=membership.role in WRITE_ROLES,
        can_administer=membership.role in ADMIN_ROLES,
    )


def can(user_id: int, organization_slug: str, capability: str) -> bool:
    allowed = CAPABILITIES.get((capability or '').strip().lower())
    if not allowed:
        return False
    membership = tenant_memberships.get_membership(user_id, organization_slug)
    return bool(
        membership
        and membership.status == 'active'
        and membership.role in allowed
    )


def require(user_id: int, organization_slug: str, capability: str) -> None:
    if not can(user_id, organization_slug, capability):
        raise PermissionError('CRM access denied.')
