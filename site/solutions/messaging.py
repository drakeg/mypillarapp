from __future__ import annotations

from pathlib import Path
import html
import json
import os
import secrets
import sqlite3
import time
from typing import Any

DATA_DIR = Path(os.environ.get('MADMALLARD_DATA_DIR', '/data'))
DB_PATH = DATA_DIR / 'madmallard.sqlite3'
PRIMARY_DOMAIN = os.environ.get('MADMALLARD_PRIMARY_DOMAIN', 'pillar.madmallards.com')
ENABLE_EMAIL = os.environ.get('MADMALLARD_ENABLE_EMAIL', 'false').strip().lower() == 'true'
NOTIFY_FROM = os.environ.get('MADMALLARD_NOTIFY_FROM', '').strip()
NOTIFY_TO = os.environ.get('MADMALLARD_NOTIFY_TO', '').strip()
AWS_REGION = os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')).strip()

STATUSES = ['new', 'waiting_on_me', 'waiting_on_client', 'in_progress', 'closed', 'spam']
PRIORITIES = ['low', 'normal', 'high']
RATINGS = ['excellent', 'good', 'ok', 'needs_improvement']


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
            lead_json TEXT NOT NULL DEFAULT '{}',
            last_feedback_rating TEXT,
            last_feedback_at INTEGER
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
            feedback_token TEXT,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            message_id INTEGER,
            token TEXT UNIQUE,
            rating TEXT NOT NULL,
            comment TEXT,
            created_at INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'visitor',
            FOREIGN KEY(conversation_id) REFERENCES conversations(id),
            FOREIGN KEY(message_id) REFERENCES messages(id)
        )
    ''')
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
    conn.execute('''
        CREATE TABLE IF NOT EXISTS customer_tokens (
            email TEXT PRIMARY KEY,
            token TEXT NOT NULL UNIQUE,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
    ''')
    for table, cols in {
        'conversations': {
            'kind': "TEXT NOT NULL DEFAULT 'chat'",
            'subject': 'TEXT',
            'company': 'TEXT',
            'priority': "TEXT NOT NULL DEFAULT 'normal'",
            'tags': "TEXT NOT NULL DEFAULT ''",
            'lead_json': "TEXT NOT NULL DEFAULT '{}'",
            'last_feedback_rating': 'TEXT',
            'last_feedback_at': 'INTEGER',
        },
        'messages': {
            'sender_type': "TEXT NOT NULL DEFAULT 'visitor'",
            'internal': 'INTEGER NOT NULL DEFAULT 0',
            'feedback_token': 'TEXT',
        },
    }.items():
        for col, ddl in cols.items():
            _ensure_column(conn, table, col, ddl)
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



def get_or_create_customer_token(email: str) -> str:
    email = (email or '').strip().lower()
    if not email:
        return ''
    ts = now()
    with db() as conn:
        row = conn.execute('SELECT token FROM customer_tokens WHERE email = ?', (email,)).fetchone()
        if row:
            conn.execute('UPDATE customer_tokens SET updated_at = ? WHERE email = ?', (ts, email))
            conn.commit()
            return row['token']
        token = secrets.token_urlsafe(24)
        conn.execute('INSERT INTO customer_tokens(email, token, created_at, updated_at) VALUES (?, ?, ?, ?)', (email, token, ts, ts))
        conn.commit()
        return token


def customer_dashboard_url(email: str) -> str:
    token = get_or_create_customer_token(email)
    return public_url(f'/my-requests/{token}') if token else ''


def get_customer_requests(customer_token: str) -> list[sqlite3.Row]:
    with db() as conn:
        row = conn.execute('SELECT email FROM customer_tokens WHERE token = ?', (customer_token,)).fetchone()
        if not row:
            return []
        return conn.execute('SELECT * FROM conversations WHERE lower(email) = lower(?) ORDER BY updated_at DESC', (row['email'],)).fetchall()


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
        if email:
            norm_email = email.strip().lower()
            row = conn.execute('SELECT token FROM customer_tokens WHERE email = ?', (norm_email,)).fetchone()
            if not row:
                conn.execute('INSERT INTO customer_tokens(email, token, created_at, updated_at) VALUES (?, ?, ?, ?)', (norm_email, secrets.token_urlsafe(24), ts, ts))
            else:
                conn.execute('UPDATE customer_tokens SET updated_at = ? WHERE email = ?', (ts, norm_email))
        conn.execute(
            'INSERT INTO leads(created_at, name, email, company, source, fields_json, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (ts, name, email, company, kind, lead_json, 'new'),
        )
        conn.commit()
        return conn.execute('SELECT * FROM conversations WHERE id = ?', (conversation_id,)).fetchone()


def add_message(token: str, *, body: str, sender: str = 'Visitor', sender_type: str = 'visitor', internal: bool = False) -> sqlite3.Row | None:
    ts = now()
    with db() as conn:
        convo = conn.execute('SELECT * FROM conversations WHERE token = ?', (token,)).fetchone()
        if not convo:
            return None
        status = convo['status']
        feedback_token = None
        if sender_type == 'admin' and not internal:
            status = 'waiting_on_client'
            feedback_token = secrets.token_urlsafe(16)
        elif sender_type == 'visitor':
            status = 'waiting_on_me'
        conn.execute(
            'INSERT INTO messages(conversation_id, created_at, sender_type, sender, body, internal, feedback_token) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (convo['id'], ts, sender_type, sender, body, 1 if internal else 0, feedback_token),
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


def list_conversations(limit: int = 100, status: str = '', q: str = '', tag: str = '') -> list[sqlite3.Row]:
    clauses = []
    params: list[Any] = []
    if status and status in STATUSES:
        clauses.append('status = ?')
        params.append(status)
    if tag:
        clauses.append('tags LIKE ?')
        params.append(f'%{tag}%')
    if q:
        clauses.append('(name LIKE ? OR email LIKE ? OR company LIKE ? OR subject LIKE ? OR tags LIKE ?)')
        params.extend([f'%{q}%'] * 5)
    where = 'WHERE ' + ' AND '.join(clauses) if clauses else ''
    with db() as conn:
        return conn.execute(f'SELECT * FROM conversations {where} ORDER BY updated_at DESC LIMIT ?', (*params, limit)).fetchall()


def inbox_stats() -> dict[str, Any]:
    with db() as conn:
        counts = {row['status']: row['count'] for row in conn.execute('SELECT status, COUNT(*) as count FROM conversations GROUP BY status')}
        total = conn.execute('SELECT COUNT(*) as c FROM conversations').fetchone()['c']
        feedback_counts = {row['rating']: row['count'] for row in conn.execute('SELECT rating, COUNT(*) as count FROM feedback GROUP BY rating')}
        recent = conn.execute('SELECT COUNT(*) as c FROM conversations WHERE created_at >= ?', (now() - 7 * 86400,)).fetchone()['c']
        return {'counts': counts, 'total': total, 'feedback': feedback_counts, 'recent': recent}


def _feedback_exists(conn: sqlite3.Connection, *, message_id: int | None = None, token: str | None = None) -> bool:
    if message_id is not None:
        row = conn.execute('SELECT id FROM feedback WHERE message_id = ? LIMIT 1', (message_id,)).fetchone()
        return row is not None
    if token:
        row = conn.execute('SELECT id FROM feedback WHERE token = ? LIMIT 1', (token,)).fetchone()
        return row is not None
    return False


def latest_feedback_target(token: str) -> sqlite3.Row | None:
    """Return the latest public admin reply that can receive visitor feedback."""
    with db() as conn:
        return conn.execute(
            """SELECT m.* FROM messages m
               JOIN conversations c ON c.id = m.conversation_id
               WHERE c.token = ?
                 AND m.sender_type = 'admin'
                 AND m.internal = 0
                 AND m.feedback_token IS NOT NULL
               ORDER BY m.id DESC LIMIT 1""",
            (token,),
        ).fetchone()


def list_feedback(token: str) -> list[sqlite3.Row]:
    with db() as conn:
        convo = conn.execute('SELECT id FROM conversations WHERE token = ?', (token,)).fetchone()
        if not convo:
            return []
        return conn.execute(
            """SELECT f.*, m.sender, m.body AS message_body, m.created_at AS message_created_at
               FROM feedback f
               LEFT JOIN messages m ON m.id = f.message_id
               WHERE f.conversation_id = ?
               ORDER BY f.created_at DESC""",
            (convo['id'],),
        ).fetchall()


def record_feedback_by_conversation(token: str, rating: str, comment: str = '') -> bool:
    """Record feedback for the latest public admin reply in a conversation.

    This keeps customer feedback optional but prevents duplicate feedback for the
    same staff response. Older versions stored conversation-level feedback only;
    this ties feedback to a specific staff message while preserving the existing
    public chat endpoint.
    """
    target = latest_feedback_target(token)
    if not target:
        return False
    return record_feedback_by_message_token(target['feedback_token'], rating, comment, source='visitor_page')


def record_feedback_by_message_token(feedback_token: str, rating: str, comment: str = '', source: str = 'email') -> bool:
    if rating not in RATINGS:
        return False
    ts = now()
    with db() as conn:
        msg = conn.execute('SELECT * FROM messages WHERE feedback_token = ?', (feedback_token,)).fetchone()
        if not msg:
            return False
        if _feedback_exists(conn, message_id=msg['id']) or _feedback_exists(conn, token=feedback_token):
            return False
        convo = conn.execute('SELECT * FROM conversations WHERE id = ?', (msg['conversation_id'],)).fetchone()
        try:
            conn.execute(
                'INSERT INTO feedback(conversation_id, message_id, token, rating, comment, created_at, source) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (msg['conversation_id'], msg['id'], feedback_token, rating, comment, ts, source),
            )
        except sqlite3.IntegrityError:
            return False
        conn.execute('UPDATE conversations SET last_feedback_rating = ?, last_feedback_at = ? WHERE id = ?', (rating, ts, msg['conversation_id']))
        conn.commit()
    notify_admin_feedback(convo['token'], rating, comment)
    return True

def _last_admin_feedback_token(convo_token: str) -> str:
    with db() as conn:
        row = conn.execute('''SELECT m.feedback_token FROM messages m JOIN conversations c ON c.id=m.conversation_id
                              WHERE c.token=? AND m.sender_type='admin' AND m.internal=0 AND m.feedback_token IS NOT NULL
                              ORDER BY m.id DESC LIMIT 1''', (convo_token,)).fetchone()
        return row['feedback_token'] if row else ''


def notify_new_conversation(convo: sqlite3.Row, first_message: str) -> None:
    admin_link = public_url(f'/admin/conversations/{convo["token"]}')
    subject = f'New {convo["kind"].replace("_", " ")} from {convo["name"] or "Visitor"}'
    details = [
        f'Name: {convo["name"] or ""}',
        f'Email: {convo["email"] or ""}',
        f'Company: {convo["company"] or ""}',
        f'Subject: {convo["subject"] or ""}',
        f'Tags: {convo["tags"] or ""}',
        '', first_message, '', f'Open in admin: {admin_link}',
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
    token = _last_admin_feedback_token(convo['token'])
    feedback = ''
    if token:
        feedback = ''.join([f'<a style="display:inline-block;margin:6px 6px 6px 0;padding:9px 12px;border-radius:999px;background:#eef7ff;color:#08233a;text-decoration:none;font-weight:700" href="{public_url(f"/feedback/{token}/{rating}")}">{label}</a>' for rating, label in [('excellent','Excellent'),('good','Good'),('ok','OK'),('needs_improvement','Needs improvement')]])
    html_body = f'<p>Greg replied:</p><blockquote>{html.escape(body)}</blockquote><p><a href="{url}">Open conversation</a></p>'
    if feedback:
        html_body += f'<hr><p><strong>Optional:</strong> How helpful was this response?</p><p>{feedback}</p>'
    send_email(
        'Greg replied to your Mad Mallard Solutions conversation',
        f'Greg replied:\n\n{body}\n\nOpen conversation: {url}',
        html_body,
        to_address=email,
    )


def notify_admin_feedback(convo_token: str, rating: str, comment: str = '') -> None:
    admin_link = public_url(f'/admin/conversations/{convo_token}')
    send_email(
        f'Conversation feedback: {rating.replace("_", " ")}',
        f'Feedback received: {rating}\n\n{comment}\n\nOpen conversation: {admin_link}',
        f'<p>Feedback received: <strong>{html.escape(rating.replace("_", " "))}</strong></p><p>{html.escape(comment)}</p><p><a href="{admin_link}">Open conversation</a></p>',
    )
