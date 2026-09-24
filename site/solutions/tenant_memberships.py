from __future__ import annotations

from dataclasses import dataclass

import tenant_auth


@dataclass(frozen=True)
class Membership:
    id: int
    user_id: int
    organization_id: int
    organization_slug: str
    organization_name: str
    role: str
    status: str


VALID_STATUSES = {'active', 'revoked'}


def _membership_from_row(row) -> Membership | None:
    if not row:
        return None
    return Membership(
        id=int(row['id']),
        user_id=int(row['user_id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        organization_name=str(row['organization_name']),
        role=str(row['role']),
        status=str(row['status']),
    )


def _select_sql() -> str:
    return '''SELECT m.id, m.user_id, m.organization_id,
                     o.slug AS organization_slug, o.name AS organization_name,
                     r.slug AS role, m.status
              FROM auth_memberships m
              JOIN auth_organizations o ON o.id = m.organization_id
              JOIN auth_roles r ON r.id = m.role_id'''


def get_membership(user_id: int, organization_slug: str) -> Membership | None:
    with tenant_auth.db() as conn:
        row = conn.execute(
            _select_sql() + '''
              WHERE m.user_id = ? AND o.slug = ?
              LIMIT 1''',
            (user_id, (organization_slug or '').strip().lower()),
        ).fetchone()
    return _membership_from_row(row)


def list_user_memberships(user_id: int, *, active_only: bool = True) -> list[Membership]:
    sql = _select_sql() + ' WHERE m.user_id = ?'
    params: list[object] = [user_id]
    if active_only:
        sql += " AND m.status = 'active' AND o.status = 'active'"
    sql += ' ORDER BY o.name, o.slug'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_membership_from_row(row) for row in rows]


def list_organization_memberships(
    organization_slug: str,
    *,
    active_only: bool = True,
) -> list[Membership]:
    sql = _select_sql() + ' WHERE o.slug = ?'
    params: list[object] = [(organization_slug or '').strip().lower()]
    if active_only:
        sql += " AND m.status = 'active'"
    sql += ' ORDER BY r.id, m.id'
    with tenant_auth.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_membership_from_row(row) for row in rows]


def grant_membership(
    user_id: int,
    organization_slug: str,
    role: str,
) -> tuple[bool, str, Membership | None]:
    normalized_role = (role or '').strip().lower()
    if normalized_role not in tenant_auth.ROLES:
        return False, 'Select a valid membership role.', None

    slug = (organization_slug or '').strip().lower()
    with tenant_auth.db() as conn:
        user = conn.execute(
            'SELECT id FROM auth_users WHERE id = ?',
            (user_id,),
        ).fetchone()
        organization = conn.execute(
            "SELECT id FROM auth_organizations WHERE slug = ? AND status = 'active'",
            (slug,),
        ).fetchone()
        role_row = conn.execute(
            'SELECT id FROM auth_roles WHERE slug = ?',
            (normalized_role,),
        ).fetchone()
        if not user:
            return False, 'User not found.', None
        if not organization:
            return False, 'Organization not found or inactive.', None
        if not role_row:
            return False, 'Membership role is not configured.', None

        timestamp = tenant_auth.now()
        conn.execute(
            '''INSERT INTO auth_memberships(
                   created_at, updated_at, user_id, organization_id, role_id, status
               ) VALUES (?, ?, ?, ?, ?, 'active')
               ON CONFLICT(user_id, organization_id) DO UPDATE SET
                   role_id = excluded.role_id,
                   status = 'active',
                   updated_at = excluded.updated_at''',
            (
                timestamp,
                timestamp,
                user_id,
                organization['id'],
                role_row['id'],
            ),
        )
        conn.commit()

    membership = get_membership(user_id, slug)
    return True, 'Membership granted.', membership


def set_membership_role(
    user_id: int,
    organization_slug: str,
    role: str,
) -> tuple[bool, str, Membership | None]:
    membership = get_membership(user_id, organization_slug)
    if not membership:
        return False, 'Membership not found.', None
    return grant_membership(user_id, organization_slug, role)


def revoke_membership(
    user_id: int,
    organization_slug: str,
) -> tuple[bool, str, Membership | None]:
    slug = (organization_slug or '').strip().lower()
    with tenant_auth.db() as conn:
        row = conn.execute(
            '''SELECT m.id
               FROM auth_memberships m
               JOIN auth_organizations o ON o.id = m.organization_id
               WHERE m.user_id = ? AND o.slug = ?''',
            (user_id, slug),
        ).fetchone()
        if not row:
            return False, 'Membership not found.', None
        conn.execute(
            "UPDATE auth_memberships SET status = 'revoked', updated_at = ? WHERE id = ?",
            (tenant_auth.now(), row['id']),
        )
        conn.commit()
    return True, 'Membership revoked.', get_membership(user_id, slug)


def has_role(user_id: int, organization_slug: str, *roles: str) -> bool:
    allowed = {(role or '').strip().lower() for role in roles}
    if not allowed or not allowed.issubset(set(tenant_auth.ROLES)):
        return False
    membership = get_membership(user_id, organization_slug)
    return bool(
        membership
        and membership.status == 'active'
        and membership.role in allowed
    )
