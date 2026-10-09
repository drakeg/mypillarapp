from __future__ import annotations

from dataclasses import dataclass

import portal_files
import portal_projects
import portal_tenancy
import portal_tickets
import tenant_auth
import tenant_memberships


READ_ROLES = {'owner', 'admin', 'staff', 'viewer'}
MANAGE_ROLES = {'owner', 'admin', 'staff'}
ADMIN_ROLES = {'owner', 'admin'}

CAPABILITIES = {
    'view': READ_ROLES,
    'projects': MANAGE_ROLES,
    'tickets': MANAGE_ROLES,
    'files': MANAGE_ROLES,
    'notifications': MANAGE_ROLES,
    'messaging': MANAGE_ROLES,
    'portal_admin': ADMIN_ROLES,
}


@dataclass(frozen=True)
class PortalStaffAccess:
    user_id: int
    organization_slug: str
    role: str
    can_view: bool
    can_manage: bool
    can_administer: bool


def _organization_is_active(organization_slug: str) -> bool:
    try:
        portal_projects._org_id(organization_slug)
        return True
    except ValueError:
        return False


def staff_access_for(
    user_id: int,
    organization_slug: str,
) -> PortalStaffAccess | None:
    if not _organization_is_active(organization_slug):
        return None
    membership = tenant_memberships.get_membership(
        user_id, organization_slug
    )
    if (
        membership is None
        or membership.status != 'active'
        or membership.role not in READ_ROLES
    ):
        return None
    return PortalStaffAccess(
        user_id=user_id,
        organization_slug=membership.organization_slug,
        role=membership.role,
        can_view=True,
        can_manage=membership.role in MANAGE_ROLES,
        can_administer=membership.role in ADMIN_ROLES,
    )


def staff_can(
    user_id: int,
    organization_slug: str,
    capability: str,
) -> bool:
    allowed = CAPABILITIES.get((capability or '').strip().lower())
    if not allowed or not _organization_is_active(organization_slug):
        return False
    membership = tenant_memberships.get_membership(
        user_id, organization_slug
    )
    return bool(
        membership
        and membership.status == 'active'
        and membership.role in allowed
    )


def require_staff(
    user_id: int,
    organization_slug: str,
    capability: str,
) -> None:
    if not staff_can(user_id, organization_slug, capability):
        raise PermissionError('Customer Portal staff access denied.')


def revalidate_customer_scope(
    scope: portal_tenancy.CustomerScope,
) -> portal_tenancy.CustomerScope:
    if scope is None:
        raise PermissionError('Customer Portal access denied.')
    with tenant_auth.db() as conn:
        email = portal_projects._validate_customer(
            conn, scope.organization_id, scope.user_id
        )
    if email != scope.email:
        raise PermissionError('Customer Portal access denied.')
    if not _organization_is_active(scope.organization_slug):
        raise PermissionError('Customer Portal access denied.')
    return scope


def customer_can_access_project(
    scope: portal_tenancy.CustomerScope,
    project_id: int,
) -> bool:
    try:
        revalidate_customer_scope(scope)
    except (PermissionError, ValueError):
        return False
    project = portal_projects.get_project(
        scope.organization_slug, int(project_id)
    )
    return bool(
        project
        and project.customer_user_id == scope.user_id
        and project.organization_id == scope.organization_id
    )


def customer_can_access_ticket(
    scope: portal_tenancy.CustomerScope,
    ticket_id: int,
) -> bool:
    try:
        revalidate_customer_scope(scope)
    except (PermissionError, ValueError):
        return False
    ticket = portal_tickets.get_ticket(
        scope.organization_slug, int(ticket_id)
    )
    return bool(
        ticket
        and ticket.customer_user_id == scope.user_id
        and ticket.organization_id == scope.organization_id
        and ticket.visibility == 'customer'
    )


def customer_can_access_file(
    scope: portal_tenancy.CustomerScope,
    file_id: int,
) -> bool:
    try:
        revalidate_customer_scope(scope)
    except (PermissionError, ValueError):
        return False
    file = portal_files.get_file(
        scope.organization_slug, int(file_id)
    )
    return bool(
        file
        and file.customer_user_id == scope.user_id
        and file.organization_id == scope.organization_id
        and file.visibility == 'customer'
    )


def require_customer_project(
    scope: portal_tenancy.CustomerScope,
    project_id: int,
):
    if not customer_can_access_project(scope, project_id):
        raise PermissionError('Customer Portal project access denied.')
    return portal_projects.get_project(scope.organization_slug, int(project_id))


def require_customer_ticket(
    scope: portal_tenancy.CustomerScope,
    ticket_id: int,
):
    if not customer_can_access_ticket(scope, ticket_id):
        raise PermissionError('Customer Portal ticket access denied.')
    return portal_tickets.get_ticket(scope.organization_slug, int(ticket_id))


def require_customer_file(
    scope: portal_tenancy.CustomerScope,
    file_id: int,
):
    if not customer_can_access_file(scope, file_id):
        raise PermissionError('Customer Portal file access denied.')
    return portal_files.get_file(scope.organization_slug, int(file_id))
