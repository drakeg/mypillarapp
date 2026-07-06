from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import html
import json
import os
import secrets
import sqlite3
import time
from typing import Any

DATA_DIR = Path('/data')
DB_PATH = DATA_DIR / 'madmallard.sqlite3'
PRIMARY_DOMAIN = os.environ.get('MADMALLARD_PRIMARY_DOMAIN', 'pillar.madmallards.com')
ENABLE_EMAIL = os.environ.get('MADMALLARD_ENABLE_EMAIL', 'false').strip().lower() == 'true'
NOTIFY_FROM = os.environ.get('MADMALLARD_NOTIFY_FROM', '').strip()
NOTIFY_TO = os.environ.get('MADMALLARD_NOTIFY_TO', '').strip()
AWS_REGION = os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')).strip()

STATUSES = ['new', 'waiting_on_me', 'waiting_on_client', 'closed']
PRIORITIES = ['low', 'normal', 'high']


def now() -> int:
    return int(time.time())


def public_url(path: str = '/') -> str:
    if not path.startswith('/'):
        path = '/' + path
    return f'https://{PRIMARY_DOMAIN}{path}'


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row['name'] == column for row in conn.execute(f'PRAGMA table_info({table})'))


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    if not _column_exists(conn, table, column):
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}')


def db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL DEFAULT 'chat',
            subject TEXT,
            name TEXT,
            email TEXT,
            company TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            priority TEXT NOT NULL DEFAULT 'normal',
            tags TEXT NOT NULL DEFAULT '',
            lead_json TEXT NOT NULL DEFAULT '{}'
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            sender_type TEXT NOT NULL DEFAULT 'visitor',
            sender TEXT NOT NULL,
            body TEXT NOT NULL,
            internal INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id)
        )
    ''')
    # Backward-compatible migrations from older bootstrap versions.
    _ensure_column(conn, 'conversations', 'kind', "TEXT NOT NULL DEFAULT 'chat'")
    _ensure_column(conn, 'conversations', 'subject', 'TEXT')
    _ensure_column(conn, 'conversations', 'company', 'TEXT')
    _ensure_column(conn, 'conversations', 'priority', "TEXT NOT NULL DEFAULT 'normal'")
    _ensure_column(conn, 'conversations', 'tags', "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, 'conversations', 'lead_json', "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, 'messages', 'sender_type', "TEXT NOT NULL DEFAULT 'visitor'")
    _ensure_column(conn, 'messages', 'internal', 'INTEGER NOT NULL DEFAULT 0')
    # Keep legacy leads table around if present/needed, but new interactions use conversations.
    conn.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at INTEGER NOT NULL,
            name TEXT,
            email TEXT,
            company TEXT,
            source TEXT NOT NULL,
            fields_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new'
        )
    ''')
    conn.commit()
    return conn


def send_email(subject: str, text_body: str, html_body: str | None = None, to_address: str | None = None) -> bool:
    if not ENABLE_EMAIL or not NOTIFY_FROM:
        return False
    destination = to_address or NOTIFY_TO
    if not destination:
        return False
    try:
        import boto3
        client = boto3.client('sesv2', region_name=AWS_REGION)
        body: dict[str, Any] = {'Text': {'Data': text_body, 'Charset': 'UTF-8'}}
        if html_body:
            body['Html'] = {'Data': html_body, 'Charset': 'UTF-8'}
        client.send_email(
            FromEmailAddress=NOTIFY_FROM,
            Destination={'ToAddresses': [destination]},
            Content={'Simple': {'Subject': {'Data': subject, 'Charset': 'UTF-8'}, 'Body': body}},
        )
        return True
    except Exception as exc:
        print(f'Email notification failed: {exc}', flush=True)
        return False


def _tag_string(values: list[str] | str | None) -> str:
    if not values:
        return ''
    if isinstance(values, str):
        values = [values]
    clean = []
    for value in values:
        value = str(value).strip()
        if value and value not in clean:
            clean.append(value)
    return ','.join(clean[:12])


def create_conversation(*, kind: str, name: str, email: str, body: str, company: str = '', subject: str = '', priority: str = 'normal', tags: list[str] | str | None = None, lead: dict | None = None) -> sqlite3.Row:
    token = secrets.token_urlsafe(18)
    ts = now()
    priority = priority if priority in PRIORITIES else 'normal'
    lead_json = json.dumps(lead or {}, sort_keys=True)
    with db() as conn:
        cur = conn.execute(
            '''INSERT INTO conversations(created_at, updated_at, token, kind, subject, name, email, company, status, priority, tags, lead_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?)''',
            (ts, ts, token, kind, subject, name, email, company, priority, _tag_string(tags), lead_json),
        )
        conversation_id = cur.lastrowid
        conn.execute(
            'INSERT INTO messages(conversation_id, created_at, sender_type, sender, body) VALUES (?, ?, ?, ?, ?)',
            (conversation_id, ts, 'visitor', name or 'Visitor', body),
        )
        conn.commit()
        convo = conn.execute('SELECT * FROM conversations WHERE id = ?', (conversation_id,)).fetchone()
    return convo


def add_message(token: str, *, body: str, sender: str = 'Visitor', sender_type: str = 'visitor', internal: bool = False) -> sqlite3.Row | None:
    ts = now()
    with db() as conn:
        convo = conn.execute('SELECT * FROM conversations WHERE token = ?', (token,)).fetchone()
        if not convo:
            return None
        status = convo['status']
        if sender_type == 'admin' and not internal:
            status = 'waiting_on_client'
        elif sender_type == 'visitor':
            status = 'waiting_on_me'
        conn.execute(
            'INSERT INTO messages(conversation_id, created_at, sender_type, sender, body, internal) VALUES (?, ?, ?, ?, ?, ?)',
            (convo['id'], ts, sender_type, sender, body, 1 if internal else 0),
        )
        conn.execute('UPDATE conversations SET updated_at = ?, status = ? WHERE id = ?', (ts, status, convo['id']))
        conn.commit()
        return conn.execute('SELECT * FROM conversations WHERE id = ?', (convo['id'],)).fetchone()


def update_conversation(token: str, *, status: str | None = None, priority: str | None = None, tags: str | None = None) -> bool:
    updates = []
    values: list[Any] = []
    if status in STATUSES:
        updates.append('status = ?')
        values.append(status)
    if priority in PRIORITIES:
        updates.append('priority = ?')
        values.append(priority)
    if tags is not None:
        updates.append('tags = ?')
        values.append(_tag_string([t.strip() for t in tags.split(',')]))
    if not updates:
        return False
    values.append(token)
    with db() as conn:
        conn.execute(f'UPDATE conversations SET {", ".join(updates)} WHERE token = ?', values)
        conn.commit()
        return True


def get_conversation(token: str) -> tuple[sqlite3.Row | None, list[sqlite3.Row]]:
    with db() as conn:
        convo = conn.execute('SELECT * FROM conversations WHERE token = ?', (token,)).fetchone()
        if not convo:
            return None, []
        messages = conn.execute('SELECT * FROM messages WHERE conversation_id = ? ORDER BY id', (convo['id'],)).fetchall()
        return convo, messages


def list_conversations(limit: int = 100) -> list[sqlite3.Row]:
    with db() as conn:
        return conn.execute('SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ?', (limit,)).fetchall()


def notify_new_conversation(convo: sqlite3.Row, first_message: str) -> None:
    admin_link = public_url(f'/admin/conversations/{convo["token"]}')
    subject = f'New {convo["kind"].replace("_", " ")} from {convo["name"] or "Visitor"}'
    details = [
        f'Name: {convo["name"] or ""}',
        f'Email: {convo["email"] or ""}',
        f'Company: {convo["company"] or ""}',
        f'Subject: {convo["subject"] or ""}',
        f'Tags: {convo["tags"] or ""}',
        '',
        first_message,
        '',
        f'Open in admin: {admin_link}',
    ]
    send_email(subject, '\n'.join(details), f'<p>{html.escape(first_message)}</p><p><a href="{admin_link}">Open in admin</a></p>')


def notify_visitor_link(convo: sqlite3.Row) -> None:
    email = (convo['email'] or '').strip()
    if not email:
        return
    url = public_url(f'/chat/{convo["token"]}')
    send_email(
        'Your Mad Mallard Solutions conversation link',
        f'Hi {convo["name"] or "there"},\n\nYour private conversation link is:\n{url}\n\nYou can bookmark this link or return to it from this email.',
        f'<p>Hi {html.escape(convo["name"] or "there")},</p><p>Your private conversation link is:</p><p><a href="{url}">{url}</a></p><p>You can bookmark this link or return to it from this email.</p>',
        to_address=email,
    )


def notify_admin_reply(convo: sqlite3.Row, sender: str, body: str) -> None:
    admin_link = public_url(f'/admin/conversations/{convo["token"]}')
    send_email(
        f'New reply from {sender or "Visitor"}',
        f'{sender or "Visitor"} replied:\n\n{body}\n\nOpen in admin: {admin_link}',
        f'<p><strong>{html.escape(sender or "Visitor")}</strong> replied:</p><blockquote>{html.escape(body)}</blockquote><p><a href="{admin_link}">Open in admin</a></p>',
    )


def notify_visitor_admin_reply(convo: sqlite3.Row, body: str) -> None:
    email = (convo['email'] or '').strip()
    if not email:
        return
    url = public_url(f'/chat/{convo["token"]}')
    send_email(
        'Greg replied to your Mad Mallard Solutions conversation',
        f'Greg replied:\n\n{body}\n\nOpen conversation: {url}',
        f'<p>Greg replied:</p><blockquote>{html.escape(body)}</blockquote><p><a href="{url}">Open conversation</a></p>',
        to_address=email,
    )
