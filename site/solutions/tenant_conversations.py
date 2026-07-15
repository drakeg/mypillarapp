from __future__ import annotations

import sqlite3

import messaging

DEFAULT_TENANT_SLUG = 'solutions'


def normalize_tenant_slug(value: str) -> str:
    return (value or '').strip().lower()


def ensure_schema() -> None:
    """Add tenant ownership to existing conversation data.

    Existing Sprint 1 records belong to the Solutions tenant. The migration is
    additive and safe to run repeatedly.
    """
    with messaging.db() as conn:
        if not messaging._column_exists(conn, 'conversations', 'organization_slug'):
            conn.execute(
                "ALTER TABLE conversations ADD COLUMN organization_slug "
                "TEXT NOT NULL DEFAULT 'solutions'"
            )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_conversations_tenant_token '
            'ON conversations(organization_slug, token)'
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_conversations_tenant_email_kind '
            'ON conversations(organization_slug, email, kind, updated_at)'
        )
        conn.commit()


def create_conversation(
    *,
    tenant_slug: str,
    kind: str,
    name: str,
    email: str,
    body: str,
    company: str = '',
    subject: str = '',
    priority: str = 'normal',
    tags: list[str] | str | None = None,
    lead: dict | None = None,
) -> sqlite3.Row:
    slug = normalize_tenant_slug(tenant_slug)
    if not slug:
        raise ValueError('tenant_slug is required')

    ensure_schema()
    conversation = messaging.create_conversation(
        kind=kind,
        name=name,
        email=email,
        body=body,
        company=company,
        subject=subject,
        priority=priority,
        tags=tags,
        lead=lead,
    )
    with messaging.db() as conn:
        conn.execute(
            'UPDATE conversations SET organization_slug = ? WHERE id = ?',
            (slug, conversation['id']),
        )
        conn.commit()
        return conn.execute(
            'SELECT * FROM conversations WHERE id = ?',
            (conversation['id'],),
        ).fetchone()


def get_conversation(tenant_slug: str, token: str) -> sqlite3.Row | None:
    slug = normalize_tenant_slug(tenant_slug)
    if not slug or not token:
        return None
    ensure_schema()
    with messaging.db() as conn:
        return conn.execute(
            '''SELECT * FROM conversations
               WHERE organization_slug = ? AND token = ?''',
            (slug, token),
        ).fetchone()


def list_customer_conversations(
    tenant_slug: str,
    email: str,
    kind: str | None = None,
) -> list[sqlite3.Row]:
    slug = normalize_tenant_slug(tenant_slug)
    normalized_email = (email or '').strip().lower()
    if not slug or not normalized_email:
        return []
    ensure_schema()
    with messaging.db() as conn:
        if kind:
            return conn.execute(
                '''SELECT * FROM conversations
                   WHERE organization_slug = ?
                     AND lower(email) = lower(?)
                     AND kind = ?
                   ORDER BY updated_at DESC, id DESC''',
                (slug, normalized_email, kind),
            ).fetchall()
        return conn.execute(
            '''SELECT * FROM conversations
               WHERE organization_slug = ?
                 AND lower(email) = lower(?)
               ORDER BY updated_at DESC, id DESC''',
            (slug, normalized_email),
        ).fetchall()


def add_message(
    tenant_slug: str,
    token: str,
    *,
    body: str,
    sender: str = 'Visitor',
    sender_type: str = 'visitor',
    internal: bool = False,
) -> sqlite3.Row | None:
    if get_conversation(tenant_slug, token) is None:
        return None
    return messaging.add_message(
        token,
        body=body,
        sender=sender,
        sender_type=sender_type,
        internal=internal,
    )


def update_conversation(
    tenant_slug: str,
    token: str,
    *,
    status: str | None = None,
    priority: str | None = None,
    tags: list[str] | str | None = None,
) -> bool:
    if get_conversation(tenant_slug, token) is None:
        return False
    return messaging.update_conversation(
        token,
        status=status,
        priority=priority,
        tags=tags,
    )
