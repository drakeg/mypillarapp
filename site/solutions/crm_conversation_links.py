from __future__ import annotations

from dataclasses import dataclass
import sqlite3

import crm_opportunities
import crm_tenancy
import tenant_auth
import tenant_conversations


@dataclass(frozen=True)
class ConversationLink:
    id: int
    organization_id: int
    organization_slug: str
    conversation_token: str
    conversation_kind: str
    company_id: int | None
    contact_id: int | None
    opportunity_id: int | None
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    crm_opportunities.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS crm_v2_conversation_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                conversation_token TEXT NOT NULL,
                conversation_kind TEXT NOT NULL,
                company_id INTEGER,
                contact_id INTEGER,
                opportunity_id INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(organization_id, conversation_token),
                FOREIGN KEY(organization_id) REFERENCES auth_organizations(id) ON DELETE CASCADE,
                FOREIGN KEY(company_id) REFERENCES crm_v2_companies(id) ON DELETE SET NULL,
                FOREIGN KEY(contact_id) REFERENCES crm_v2_contacts(id) ON DELETE SET NULL,
                FOREIGN KEY(opportunity_id) REFERENCES crm_v2_opportunities(id) ON DELETE SET NULL
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_crm_v2_conversation_links_org_contact '
            'ON crm_v2_conversation_links(organization_id, contact_id, id)'
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_crm_v2_conversation_links_org_opportunity '
            'ON crm_v2_conversation_links(organization_id, opportunity_id, id)'
        )
        conn.commit()


def _validate_crm_links(
    conn: sqlite3.Connection,
    organization_id: int,
    company_id: int | None,
    contact_id: int | None,
    opportunity_id: int | None,
) -> None:
    for table, record_id in (
        ('crm_v2_companies', company_id),
        ('crm_v2_contacts', contact_id),
        ('crm_v2_opportunities', opportunity_id),
    ):
        crm_tenancy.ensure_same_organization(
            conn,
            organization_id=organization_id,
            table=table,
            record_id=record_id,
        )

    if company_id is not None and contact_id is not None:
        contact = conn.execute(
            'SELECT company_id FROM crm_v2_contacts WHERE id=? AND organization_id=?',
            (contact_id, organization_id),
        ).fetchone()
        if contact and contact['company_id'] is not None and int(contact['company_id']) != company_id:
            raise ValueError('Conversation link company does not match the contact company.')

    if opportunity_id is not None:
        opportunity = conn.execute(
            'SELECT company_id, contact_id FROM crm_v2_opportunities WHERE id=? AND organization_id=?',
            (opportunity_id, organization_id),
        ).fetchone()
        if opportunity is None:
            raise ValueError('Conversation link opportunity is unavailable.')
        if company_id is not None and opportunity['company_id'] is not None:
            if company_id != int(opportunity['company_id']):
                raise ValueError('Conversation link company does not match the opportunity company.')
        if contact_id is not None and opportunity['contact_id'] is not None:
            if contact_id != int(opportunity['contact_id']):
                raise ValueError('Conversation link contact does not match the opportunity contact.')


def link_conversation(
    organization_slug: str,
    conversation_token: str,
    *,
    company_id: int | None = None,
    contact_id: int | None = None,
    opportunity_id: int | None = None,
) -> ConversationLink:
    organization_id = crm_tenancy.organization_id(organization_slug)
    conversation_token = (conversation_token or '').strip()
    if not conversation_token:
        raise ValueError('Conversation token is required.')

    conversation = tenant_conversations.get_conversation(
        organization_slug, conversation_token
    )
    if conversation is None:
        raise ValueError('Conversation is missing or belongs to another organization.')

    ensure_schema()
    timestamp = tenant_auth.now()
    with tenant_auth.db() as conn:
        _validate_crm_links(
            conn, organization_id, company_id, contact_id, opportunity_id
        )
        existing = conn.execute(
            '''
            SELECT id FROM crm_v2_conversation_links
            WHERE organization_id=? AND conversation_token=?
            ''',
            (organization_id, conversation_token),
        ).fetchone()
        if existing:
            conn.execute(
                '''
                UPDATE crm_v2_conversation_links
                SET conversation_kind=?, company_id=?, contact_id=?,
                    opportunity_id=?, updated_at=?
                WHERE organization_id=? AND conversation_token=?
                ''',
                (
                    str(conversation['kind']), company_id, contact_id,
                    opportunity_id, timestamp, organization_id, conversation_token,
                ),
            )
        else:
            conn.execute(
                '''
                INSERT INTO crm_v2_conversation_links(
                    organization_id, conversation_token, conversation_kind,
                    company_id, contact_id, opportunity_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    organization_id, conversation_token, str(conversation['kind']),
                    company_id, contact_id, opportunity_id, timestamp, timestamp,
                ),
            )
        conn.commit()
        row = _select(conn, organization_id, conversation_token)
    return _from_row(row)


def get_link(
    organization_slug: str,
    conversation_token: str,
) -> ConversationLink | None:
    organization_id = crm_tenancy.organization_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        row = _select(conn, organization_id, conversation_token)
    return _from_row(row) if row else None


def list_links(
    organization_slug: str,
    *,
    company_id: int | None = None,
    contact_id: int | None = None,
    opportunity_id: int | None = None,
) -> list[ConversationLink]:
    organization_id = crm_tenancy.organization_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        _validate_crm_links(
            conn, organization_id, company_id, contact_id, opportunity_id
        )
        sql = '''
            SELECT l.*, o.slug AS organization_slug
            FROM crm_v2_conversation_links l
            JOIN auth_organizations o ON o.id=l.organization_id
            WHERE l.organization_id=?
        '''
        params: list[object] = [organization_id]
        for field, value in (
            ('company_id', company_id),
            ('contact_id', contact_id),
            ('opportunity_id', opportunity_id),
        ):
            if value is not None:
                sql += f' AND l.{field}=?'
                params.append(value)
        sql += ' ORDER BY l.updated_at DESC, l.id DESC'
        rows = conn.execute(sql, params).fetchall()
    return [_from_row(row) for row in rows]


def unlink_conversation(
    organization_slug: str,
    conversation_token: str,
) -> bool:
    organization_id = crm_tenancy.organization_id(organization_slug)
    ensure_schema()
    with tenant_auth.db() as conn:
        cur = conn.execute(
            '''
            DELETE FROM crm_v2_conversation_links
            WHERE organization_id=? AND conversation_token=?
            ''',
            (organization_id, conversation_token),
        )
        conn.commit()
        return cur.rowcount > 0


def _select(conn: sqlite3.Connection, organization_id: int, conversation_token: str):
    return conn.execute(
        '''
        SELECT l.*, o.slug AS organization_slug
        FROM crm_v2_conversation_links l
        JOIN auth_organizations o ON o.id=l.organization_id
        WHERE l.organization_id=? AND l.conversation_token=?
        LIMIT 1
        ''',
        (organization_id, conversation_token),
    ).fetchone()


def _from_row(row) -> ConversationLink:
    return ConversationLink(
        id=int(row['id']),
        organization_id=int(row['organization_id']),
        organization_slug=str(row['organization_slug']),
        conversation_token=str(row['conversation_token']),
        conversation_kind=str(row['conversation_kind']),
        company_id=int(row['company_id']) if row['company_id'] is not None else None,
        contact_id=int(row['contact_id']) if row['contact_id'] is not None else None,
        opportunity_id=int(row['opportunity_id']) if row['opportunity_id'] is not None else None,
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
