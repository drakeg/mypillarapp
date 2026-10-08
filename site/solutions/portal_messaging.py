from __future__ import annotations

from dataclasses import dataclass
import sqlite3

import messaging
import portal_projects
import portal_tenancy
import portal_tickets
import tenant_auth
import tenant_conversations


@dataclass(frozen=True)
class PortalConversationLink:
    id: int
    organization_id: int
    organization_slug: str
    conversation_token: str
    customer_user_id: int
    customer_email: str
    project_id: int | None
    ticket_id: int | None
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    portal_tickets.ensure_schema()
    tenant_conversations.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS portal_conversation_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                conversation_token TEXT NOT NULL,
                customer_user_id INTEGER NOT NULL,
                customer_email TEXT NOT NULL COLLATE NOCASE,
                project_id INTEGER,
                ticket_id INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(organization_id, conversation_token),
                FOREIGN KEY(organization_id)
                    REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(customer_user_id)
                    REFERENCES auth_users(id) ON DELETE RESTRICT,
                FOREIGN KEY(project_id)
                    REFERENCES portal_projects(id) ON DELETE SET NULL,
                FOREIGN KEY(ticket_id)
                    REFERENCES portal_tickets(id) ON DELETE SET NULL
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_portal_conversation_links_org_customer '
            'ON portal_conversation_links(organization_id, customer_user_id, updated_at DESC, id DESC)'
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_portal_conversation_links_org_project '
            'ON portal_conversation_links(organization_id, project_id, id)'
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_portal_conversation_links_org_ticket '
            'ON portal_conversation_links(organization_id, ticket_id, id)'
        )
        conn.commit()


def _validate_customer(
    conn: sqlite3.Connection,
    organization_id: int,
    customer_user_id: int,
) -> str:
    return portal_projects._validate_customer(
        conn, organization_id, customer_user_id
    )


def _validate_relationships(
    conn: sqlite3.Connection,
    organization_id: int,
    customer_user_id: int,
    project_id: int | None,
    ticket_id: int | None,
) -> None:
    project_row = None
    if project_id is not None:
        project_row = conn.execute(
            '''
            SELECT customer_user_id, status
            FROM portal_projects
            WHERE id=? AND organization_id=?
            ''',
            (int(project_id), organization_id),
        ).fetchone()
        if project_row is None:
            raise ValueError(
                'Conversation project is missing or belongs to another organization.'
            )
        if int(project_row['customer_user_id']) != int(customer_user_id):
            raise ValueError(
                'Conversation customer does not match the project customer.'
            )

    if ticket_id is None:
        return

    ticket_row = conn.execute(
        '''
        SELECT customer_user_id, project_id, status
        FROM portal_tickets
        WHERE id=? AND organization_id=?
        ''',
        (int(ticket_id), organization_id),
    ).fetchone()
    if ticket_row is None:
        raise ValueError(
            'Conversation ticket is missing or belongs to another organization.'
        )
    if int(ticket_row['customer_user_id']) != int(customer_user_id):
        raise ValueError(
            'Conversation customer does not match the ticket customer.'
        )
    if (
        project_id is not None
        and ticket_row['project_id'] is not None
        and int(ticket_row['project_id']) != int(project_id)
    ):
        raise ValueError(
            'Conversation project does not match the ticket project.'
        )


def link_conversation(
    organization_slug: str,
    conversation_token: str,
    *,
    customer_user_id: int,
    project_id: int | None = None,
    ticket_id: int | None = None,
) -> PortalConversationLink:
    organization_id = portal_projects._org_id(organization_slug)
    token = (conversation_token or '').strip()
    if not token:
        raise ValueError('Conversation token is required.')

    conversation = tenant_conversations.get_conversation(
        organization_slug, token
    )
    if conversation is None:
        raise ValueError(
            'Conversation is missing or belongs to another organization.'
        )

    ensure_schema()
    now = tenant_auth.now()
    with tenant_auth.db() as conn:
        customer_email = _validate_customer(
            conn, organization_id, customer_user_id
        )
        if (
            str(conversation['email'] or '').strip().lower()
            != customer_email
        ):
            raise ValueError(
                'Conversation customer does not match the portal customer.'
            )
        _validate_relationships(
            conn,
            organization_id,
            customer_user_id,
            project_id,
            ticket_id,
        )

        existing = conn.execute(
            '''
            SELECT id FROM portal_conversation_links
            WHERE organization_id=? AND conversation_token=?
            ''',
            (organization_id, token),
        ).fetchone()
        if existing:
            conn.execute(
                '''
                UPDATE portal_conversation_links
                SET customer_user_id=?, customer_email=?,
                    project_id=?, ticket_id=?, updated_at=?
                WHERE organization_id=? AND conversation_token=?
                ''',
                (
                    int(customer_user_id),
                    customer_email,
                    project_id,
                    ticket_id,
                    now,
                    organization_id,
                    token,
                ),
            )
        else:
            conn.execute(
                '''
                INSERT INTO portal_conversation_links(
                    organization_id, conversation_token,
                    customer_user_id, customer_email,
                    project_id, ticket_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    organization_id,
                    token,
                    int(customer_user_id),
                    customer_email,
                    project_id,
                    ticket_id,
                    now,
                    now,
                ),
            )
        conn.commit()
        row = _select_link(conn, organization_id, token)
    return _from_link(row)


def list_links(
    organization_slug: str,
    *,
    customer_user_id: int | None = None,
    project_id: int | None = None,
    ticket_id: int | None = None,
) -> list[PortalConversationLink]:
    organization_id = portal_projects._org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        if customer_user_id is not None:
            _validate_customer(conn, organization_id, customer_user_id)
        if project_id is not None:
            project = conn.execute(
                '''
                SELECT customer_user_id FROM portal_projects
                WHERE id=? AND organization_id=?
                ''',
                (int(project_id), organization_id),
            ).fetchone()
            if project is None:
                raise ValueError(
                    'Conversation project is missing or belongs to another organization.'
                )
            if (
                customer_user_id is not None
                and int(project['customer_user_id']) != int(customer_user_id)
            ):
                raise ValueError(
                    'Conversation project does not belong to the requested customer.'
                )
        if ticket_id is not None:
            ticket = conn.execute(
                '''
                SELECT customer_user_id, project_id FROM portal_tickets
                WHERE id=? AND organization_id=?
                ''',
                (int(ticket_id), organization_id),
            ).fetchone()
            if ticket is None:
                raise ValueError(
                    'Conversation ticket is missing or belongs to another organization.'
                )
            if (
                customer_user_id is not None
                and int(ticket['customer_user_id']) != int(customer_user_id)
            ):
                raise ValueError(
                    'Conversation ticket does not belong to the requested customer.'
                )
            if (
                project_id is not None
                and ticket['project_id'] is not None
                and int(ticket['project_id']) != int(project_id)
            ):
                raise ValueError(
                    'Conversation ticket does not belong to the requested project.'
                )

        sql = '''
            SELECT l.*, o.slug AS organization_slug
            FROM portal_conversation_links l
            JOIN auth_organizations o ON o.id=l.organization_id
            WHERE l.organization_id=?
        '''
        params: list[object] = [organization_id]
        if customer_user_id is not None:
            sql += ' AND l.customer_user_id=?'
            params.append(int(customer_user_id))
        if project_id is not None:
            sql += ' AND l.project_id=?'
            params.append(int(project_id))
        if ticket_id is not None:
            sql += ' AND l.ticket_id=?'
            params.append(int(ticket_id))
        sql += ' ORDER BY l.updated_at DESC, l.id DESC'
        rows = conn.execute(sql, params).fetchall()
    return [_from_link(row) for row in rows]


def list_customer_messages(
    scope: portal_tenancy.CustomerScope,
    conversation_token: str,
) -> list[sqlite3.Row]:
    conversation = portal_tenancy.conversation_for_customer(
        scope, conversation_token
    )
    if conversation is None:
        return []
    with messaging.db() as conn:
        return conn.execute(
            '''
            SELECT * FROM messages
            WHERE conversation_id=? AND internal=0
            ORDER BY created_at ASC, id ASC
            ''',
            (conversation['id'],),
        ).fetchall()


def add_customer_reply(
    scope: portal_tenancy.CustomerScope,
    conversation_token: str,
    *,
    body: str,
    sender: str = 'Customer',
) -> sqlite3.Row | None:
    body = (body or '').strip()
    if not body:
        raise ValueError('Message body is required.')
    if len(body) > 10000:
        raise ValueError('Message body must be 10000 characters or fewer.')
    conversation = portal_tenancy.conversation_for_customer(
        scope, conversation_token
    )
    if conversation is None:
        return None
    return tenant_conversations.add_message(
        scope.organization_slug,
        conversation_token,
        body=body,
        sender=(sender or 'Customer').strip() or 'Customer',
        sender_type='visitor',
        internal=False,
    )


def unlink_conversation(
    organization_slug: str,
    conversation_token: str,
) -> bool:
    organization_id = portal_projects._org_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        cur = conn.execute(
            '''
            DELETE FROM portal_conversation_links
            WHERE organization_id=? AND conversation_token=?
            ''',
            (organization_id, (conversation_token or '').strip()),
        )
        conn.commit()
        return cur.rowcount > 0


def _select_link(
    conn: sqlite3.Connection,
    organization_id: int,
    conversation_token: str,
):
    return conn.execute(
        '''
        SELECT l.*, o.slug AS organization_slug
        FROM portal_conversation_links l
        JOIN auth_organizations o ON o.id=l.organization_id
        WHERE l.organization_id=? AND l.conversation_token=?
        LIMIT 1
        ''',
        (organization_id, conversation_token),
    ).fetchone()


def _from_link(row) -> PortalConversationLink:
    return PortalConversationLink(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        conversation_token=str(row['conversation_token']),
        customer_user_id=int(row['customer_user_id']),
        customer_email=str(row['customer_email']),
        project_id=(
            int(row['project_id']) if row['project_id'] is not None else None
        ),
        ticket_id=(
            int(row['ticket_id']) if row['ticket_id'] is not None else None
        ),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
