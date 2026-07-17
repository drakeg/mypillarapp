from __future__ import annotations

from dataclasses import dataclass

import tenant_auth
import tenant_context


PROTECTED_TENANTS = {'solutions'}
VALID_ACTIONS = {'suspend', 'reactivate', 'archive'}


@dataclass(frozen=True)
class LifecycleResult:
    organization_slug: str
    previous_status: str
    current_status: str
    sessions_revoked: int
    tokens_revoked: int
    domains_active: bool


def change_tenant_status(
    organization_slug: str,
    action: str,
) -> tuple[bool, str, LifecycleResult | None]:
    slug = (organization_slug or '').strip().lower()
    normalized_action = (action or '').strip().lower()

    if normalized_action not in VALID_ACTIONS:
        return False, 'Lifecycle action must be suspend, reactivate, or archive.', None
    if slug in PROTECTED_TENANTS and normalized_action != 'reactivate':
        return False, 'The primary Solutions tenant cannot be suspended or archived.', None

    tenant_context.ensure_schema()
    with tenant_auth.db() as conn:
        organization = conn.execute(
            'SELECT id, slug, status FROM auth_organizations WHERE slug = ?',
            (slug,),
        ).fetchone()
        if not organization:
            return False, 'Organization not found.', None

        previous_status = str(organization['status'])
        if normalized_action == 'reactivate':
            current_status = 'active'
            domains_active = 1
        elif normalized_action == 'suspend':
            current_status = 'inactive'
            domains_active = 0
        else:
            current_status = 'archived'
            domains_active = 0

        if previous_status == current_status:
            return False, f'Organization is already {current_status}.', None
        if previous_status == 'archived' and normalized_action != 'reactivate':
            return False, 'Archived organizations can only be reactivated.', None

        timestamp = tenant_auth.now()
        organization_id = int(organization['id'])
        conn.execute(
            'UPDATE auth_organizations SET status = ?, updated_at = ? WHERE id = ?',
            (current_status, timestamp, organization_id),
        )
        conn.execute(
            'UPDATE tenant_domains SET is_active = ?, updated_at = ? WHERE organization_id = ?',
            (domains_active, timestamp, organization_id),
        )

        sessions_revoked = 0
        tokens_revoked = 0
        if current_status != 'active':
            user_rows = conn.execute(
                'SELECT id FROM auth_users WHERE organization_id = ?',
                (organization_id,),
            ).fetchall()
            user_ids = [int(row['id']) for row in user_rows]
            if user_ids:
                placeholders = ','.join('?' for _ in user_ids)
                sessions_revoked = conn.execute(
                    f'DELETE FROM auth_sessions WHERE user_id IN ({placeholders})',
                    user_ids,
                ).rowcount
                tokens_revoked = conn.execute(
                    f'DELETE FROM auth_tokens WHERE user_id IN ({placeholders})',
                    user_ids,
                ).rowcount

        conn.commit()

    result = LifecycleResult(
        organization_slug=slug,
        previous_status=previous_status,
        current_status=current_status,
        sessions_revoked=max(int(sessions_revoked or 0), 0),
        tokens_revoked=max(int(tokens_revoked or 0), 0),
        domains_active=bool(domains_active),
    )
    return True, f'Organization {current_status}.', result


def suspend_tenant(organization_slug: str):
    return change_tenant_status(organization_slug, 'suspend')


def reactivate_tenant(organization_slug: str):
    return change_tenant_status(organization_slug, 'reactivate')


def archive_tenant(organization_slug: str):
    return change_tenant_status(organization_slug, 'archive')
