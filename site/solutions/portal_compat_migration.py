from __future__ import annotations

from dataclasses import dataclass

import portal_messaging
import portal_tenancy
import tenant_auth
import tenant_conversations


@dataclass(frozen=True)
class PortalCompatibilityResult:
    conversations_linked: int
    already_linked: int
    unmatched_customers: int


def migrate_existing_customer_history() -> PortalCompatibilityResult:
    """Add portal metadata to safely matchable legacy conversations.

    Existing conversation/request rows remain authoritative and untouched.
    Existing portal conversation links are never overwritten.
    """
    audit = portal_tenancy.audit_existing_customer_history()
    if not audit.safe_for_portal_foundation:
        raise ValueError(
            'Existing customer history is not safe to migrate: '
            f'missing_customer_email={audit.missing_customer_email}, '
            f'unknown_organization_rows={audit.unknown_organization_rows}.'
        )

    portal_messaging.ensure_schema()
    tenant_conversations.ensure_schema()

    linked = 0
    already_linked = 0
    unmatched = 0

    with tenant_auth.db() as conn:
        conversations = conn.execute(
            '''
            SELECT token, organization_slug, lower(trim(email)) AS email
            FROM conversations
            ORDER BY id
            '''
        ).fetchall()

        for conversation in conversations:
            token = str(conversation['token'])
            slug = str(conversation['organization_slug']).strip().lower()
            email = str(conversation['email'] or '').strip().lower()

            existing = conn.execute(
                '''
                SELECT id
                FROM portal_conversation_links
                WHERE organization_id=(
                    SELECT id FROM auth_organizations WHERE slug=?
                )
                  AND conversation_token=?
                LIMIT 1
                ''',
                (slug, token),
            ).fetchone()
            if existing is not None:
                already_linked += 1
                continue

            matches = conn.execute(
                '''
                SELECT u.id
                FROM auth_users u
                JOIN auth_organizations o
                  ON o.id=u.organization_id
                JOIN auth_memberships m
                  ON m.user_id=u.id
                 AND m.organization_id=o.id
                 AND m.status='active'
                WHERE o.slug=?
                  AND o.status='active'
                  AND u.is_active=1
                  AND lower(trim(u.email))=?
                ORDER BY u.id
                ''',
                (slug, email),
            ).fetchall()

            if len(matches) != 1:
                unmatched += 1
                continue

            portal_messaging.link_conversation(
                slug,
                token,
                customer_user_id=int(matches[0]['id']),
            )
            linked += 1

    return PortalCompatibilityResult(
        conversations_linked=linked,
        already_linked=already_linked,
        unmatched_customers=unmatched,
    )
