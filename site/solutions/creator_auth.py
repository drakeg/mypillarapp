from __future__ import annotations

from dataclasses import dataclass

import tenant_auth
import tenant_memberships
import tenant_sites


READ_ROLES={'owner','admin','staff','viewer'}
MANAGE_ROLES={'owner','admin','staff'}
ADMIN_ROLES={'owner','admin'}

CAPABILITIES={
    'view':READ_ROLES,
    'profiles':MANAGE_ROLES,
    'links':MANAGE_ROLES,
    'affiliates':MANAGE_ROLES,
    'collections':MANAGE_ROLES,
    'downloads':MANAGE_ROLES,
    'products':MANAGE_ROLES,
    'analytics':READ_ROLES,
    'creator_admin':ADMIN_ROLES,
}


@dataclass(frozen=True)
class CreatorAccess:
    user_id:int
    organization_slug:str
    role:str
    can_view:bool
    can_manage:bool
    can_administer:bool


def _active_user_and_org(user_id:int,organization_slug:str)->bool:
    with tenant_auth.db() as conn:
        user=conn.execute(
            'SELECT is_active FROM auth_users WHERE id=? LIMIT 1',
            (int(user_id),),
        ).fetchone()
        organization=conn.execute(
            'SELECT status FROM auth_organizations WHERE slug=? LIMIT 1',
            ((organization_slug or '').strip().lower(),),
        ).fetchone()
    return bool(
        user
        and int(user['is_active'])==1
        and organization
        and organization['status']=='active'
    )


def access_for(user_id:int,organization_slug:str)->CreatorAccess|None:
    if not _active_user_and_org(user_id,organization_slug):
        return None
    membership=tenant_memberships.get_membership(user_id,organization_slug)
    if not membership or membership.status!='active' or membership.role not in READ_ROLES:
        return None
    return CreatorAccess(
        user_id=int(user_id),
        organization_slug=membership.organization_slug,
        role=membership.role,
        can_view=True,
        can_manage=membership.role in MANAGE_ROLES,
        can_administer=membership.role in ADMIN_ROLES,
    )


def can(user_id:int,organization_slug:str,capability:str)->bool:
    allowed=CAPABILITIES.get((capability or '').strip().lower())
    if not allowed or not _active_user_and_org(user_id,organization_slug):
        return False
    membership=tenant_memberships.get_membership(user_id,organization_slug)
    return bool(
        membership
        and membership.status=='active'
        and membership.role in allowed
    )


def can_site(
    user_id:int,
    organization_slug:str,
    site_slug:str,
    capability:str,
)->bool:
    site=tenant_sites.get_site(organization_slug,site_slug)
    return bool(
        site
        and site.status!='archived'
        and can(user_id,organization_slug,capability)
    )


def require(
    user_id:int,
    organization_slug:str,
    capability:str,
)->None:
    if not can(user_id,organization_slug,capability):
        raise PermissionError('Creator administration access denied.')


def require_site(
    user_id:int,
    organization_slug:str,
    site_slug:str,
    capability:str,
)->None:
    if not can_site(user_id,organization_slug,site_slug,capability):
        raise PermissionError('Creator site administration access denied.')
