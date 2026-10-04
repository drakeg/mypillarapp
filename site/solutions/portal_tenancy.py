from __future__ import annotations

from dataclasses import dataclass
import sqlite3

import tenant_auth
import tenant_conversations


@dataclass(frozen=True)
class CustomerScope:
    user_id: int
    organization_id: int
    organization_slug: str
    email: str


@dataclass(frozen=True)
class PortalLegacyAudit:
    conversations: int
    project_requests: int
    chats: int
    missing_customer_email: int
    unknown_organization_rows: int

    @property
    def safe_for_portal_foundation(self) -> bool:
        return (
            self.missing_customer_email == 0
            and self.unknown_organization_rows == 0
        )


def customer_scope(user: sqlite3.Row) -> CustomerScope:
    if user is None:
        raise ValueError('Authenticated customer is required.')

    try:
        user_id = int(user['id'])
        organization_slug = str(user['organization_slug']).strip().lower()
        email = str(user['email']).strip().lower()
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ValueError('Authenticated customer context is incomplete.') from exc

    if not organization_slug or not email:
        raise ValueError('Authenticated customer context is incomplete.')

    with tenant_auth.db() as conn:
        row = conn.execute(
            """SELECT o.id
               FROM auth_users u
               JOIN auth_memberships m
                 ON m.user_id=u.id AND m.organization_id=o.id
               JOIN auth_organizations o
                 ON o.id=u.organization_id
               WHERE u.id=? AND o.slug=? AND o.status='active'
                 AND u.is_active=1
                 AND m.status='active'
               LIMIT 1""",
            (user_id, organization_slug),
        ).fetchone()
    if row is None:
        raise ValueError('Customer is not active for this organization.')

    return CustomerScope(
        user_id=user_id,
        organization_id=int(row['id']),
        organization_slug=organization_slug,
        email=email,
    )


def conversation_for_customer(
    scope: CustomerScope,
    token: str,
) -> sqlite3.Row | None:
    conversation = tenant_conversations.get_conversation(
        scope.organization_slug, (token or '').strip()
    )
    if conversation is None:
        return None
    if str(conversation['email'] or '').strip().lower() != scope.email:
        return None
    return conversation


def list_customer_history(
    scope: CustomerScope,
    *,
    kind: str | None = None,
) -> list[sqlite3.Row]:
    return tenant_conversations.list_customer_conversations(
        scope.organization_slug,
        scope.email,
        kind,
    )


def audit_existing_customer_history() -> PortalLegacyAudit:
    tenant_conversations.ensure_schema()
    with tenant_auth.db() as conn:
        row = conn.execute(
            """SELECT
                   COUNT(*) AS conversations,
                   SUM(CASE WHEN c.kind='project_request' THEN 1 ELSE 0 END)
                       AS project_requests,
                   SUM(CASE WHEN c.kind='chat' THEN 1 ELSE 0 END) AS chats,
                   SUM(CASE WHEN trim(COALESCE(c.email,''))='' THEN 1 ELSE 0 END)
                       AS missing_customer_email,
                   SUM(CASE WHEN o.id IS NULL THEN 1 ELSE 0 END)
                       AS unknown_organization_rows
               FROM conversations c
               LEFT JOIN auth_organizations o
                 ON o.slug=c.organization_slug"""
        ).fetchone()

    return PortalLegacyAudit(
        conversations=int(row['conversations'] or 0),
        project_requests=int(row['project_requests'] or 0),
        chats=int(row['chats'] or 0),
        missing_customer_email=int(row['missing_customer_email'] or 0),
        unknown_organization_rows=int(row['unknown_organization_rows'] or 0),
    )
