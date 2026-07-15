from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote
import base64
import hashlib
import hmac
import html
import os
import secrets
import sqlite3
import time

import messaging
import tenant_conversations

DATA_DIR = Path(os.environ.get('MADMALLARD_DATA_DIR', '/data'))
DB_PATH = DATA_DIR / 'madmallard.sqlite3'
PRIMARY_DOMAIN = os.environ.get('MADMALLARD_PRIMARY_DOMAIN', 'pillar.madmallards.com')
SESSION_COOKIE = 'mmp_user_session'
SESSION_MAX_AGE = 60 * 60 * 24 * 30
PBKDF2_ITERATIONS = 310_000
ROLES = ('owner', 'admin', 'staff', 'viewer')


def now() -> int:
    return int(time.time())


def esc(value: object) -> str:
    return html.escape(str(value or ''))


def public_url(path: str, host: str = '') -> str:
    if not path.startswith('/'):
        path = '/' + path
    public_host = (host or PRIMARY_DOMAIN).strip().lower().rstrip('.')
    if '://' in public_host:
        public_host = public_host.split('://', 1)[1]
    public_host = public_host.split('/', 1)[0].split(',', 1)[0].strip()
    if not public_host:
        public_host = PRIMARY_DOMAIN
    return f'https://{public_host}{path}'


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        ensure_schema(conn)
        yield conn
    finally:
        conn.close()


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS auth_organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS auth_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            organization_id INTEGER NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            first_name TEXT NOT NULL DEFAULT '',
            last_name TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            is_active INTEGER NOT NULL DEFAULT 0,
            email_verified_at INTEGER,
            last_login_at INTEGER,
            FOREIGN KEY(organization_id) REFERENCES auth_organizations(id)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS auth_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            purpose TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            used_at INTEGER,
            FOREIGN KEY(user_id) REFERENCES auth_users(id) ON DELETE CASCADE
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            last_seen_at INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES auth_users(id) ON DELETE CASCADE
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_auth_tokens_lookup ON auth_tokens(token_hash, purpose, expires_at)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_auth_sessions_lookup ON auth_sessions(token_hash, expires_at)')
    seed_organizations(conn)
    conn.commit()


def seed_organizations(conn: sqlite3.Connection) -> None:
    ts = now()
    organizations = (
        ('solutions', 'Mad Mallard Solutions'),
        ('personal-training', 'Mad Mallard Personal Training'),
        ('adventures', 'Mad Mallards Adventures'),
    )
    for slug, name in organizations:
        conn.execute(
            '''INSERT INTO auth_organizations(created_at, updated_at, slug, name, status)
               VALUES (?, ?, ?, ?, 'active')
               ON CONFLICT(slug) DO UPDATE SET name = excluded.name, updated_at = excluded.updated_at''',
            (ts, ts, slug, name),
        )


def list_organizations() -> list[sqlite3.Row]:
    with db() as conn:
        return conn.execute("SELECT * FROM auth_organizations WHERE status = 'active' ORDER BY name").fetchall()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def hash_password(password: str) -> str:
    salt = _b64(secrets.token_bytes(18))
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), PBKDF2_ITERATIONS).hex()
    return f'pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split('$', 3)
        if algorithm != 'pbkdf2_sha256':
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), int(iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _new_token(conn: sqlite3.Connection, user_id: int, purpose: str, ttl: int) -> str:
    token = secrets.token_urlsafe(32)
    ts = now()
    conn.execute('DELETE FROM auth_tokens WHERE user_id = ? AND purpose = ? AND used_at IS NULL', (user_id, purpose))
    conn.execute(
        'INSERT INTO auth_tokens(user_id, purpose, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?, ?)',
        (user_id, purpose, _token_hash(token), ts, ts + ttl),
    )
    return token


def _new_session(conn: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(40)
    ts = now()
    conn.execute(
        'INSERT INTO auth_sessions(user_id, token_hash, created_at, expires_at, last_seen_at) VALUES (?, ?, ?, ?, ?)',
        (user_id, _token_hash(token), ts, ts + SESSION_MAX_AGE, ts),
    )
    return token


def register_user(*, organization_slug: str, first_name: str, last_name: str, email: str, password: str, public_host: str = '') -> tuple[bool, str]:
    email = email.strip().lower()
    first_name = first_name.strip()
    last_name = last_name.strip()
    if not email or '@' not in email:
        return False, 'Enter a valid email address.'
    if len(password) < 12:
        return False, 'Password must be at least 12 characters.'
    if not first_name or not last_name:
        return False, 'First and last name are required.'
    with db() as conn:
        org = conn.execute("SELECT * FROM auth_organizations WHERE slug = ? AND status = 'active'", (organization_slug,)).fetchone()
        if not org:
            return False, 'Select a valid organization.'
        existing = conn.execute('SELECT id FROM auth_users WHERE lower(email) = lower(?)', (email,)).fetchone()
        if existing:
            return False, 'An account already exists for that email address.'
        ts = now()
        role = 'viewer'
        cur = conn.execute(
            '''INSERT INTO auth_users(created_at, updated_at, organization_id, email, first_name, last_name, password_hash, role, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)''',
            (ts, ts, org['id'], email, first_name, last_name, hash_password(password), role),
        )
        user_id = int(cur.lastrowid)
        token = _new_token(conn, user_id, 'verify_email', 60 * 60 * 24)
        conn.commit()
    verify_url = public_url(f'/verify-email/{quote(token)}', public_host)
    messaging.send_email(
        'Verify your Mad Mallard Platform account',
        f'Hello {first_name},\n\nVerify your account:\n{verify_url}\n\nThis link expires in 24 hours.',
        f'<p>Hello {esc(first_name)},</p><p>Verify your account:</p><p><a href="{esc(verify_url)}">Verify email address</a></p><p>This link expires in 24 hours.</p>',
        email,
    )
    return True, 'Check your email for a verification link.'


def verify_email(token: str) -> tuple[bool, str, str]:
    ts = now()
    with db() as conn:
        row = conn.execute(
            '''SELECT t.id AS token_id, t.user_id, u.email
               FROM auth_tokens t JOIN auth_users u ON u.id = t.user_id
               WHERE t.token_hash = ? AND t.purpose = 'verify_email' AND t.used_at IS NULL AND t.expires_at >= ?''',
            (_token_hash(token), ts),
        ).fetchone()
        if not row:
            return False, 'This verification link is invalid or expired.', ''
        conn.execute('UPDATE auth_tokens SET used_at = ? WHERE id = ?', (ts, row['token_id']))
        conn.execute('UPDATE auth_users SET is_active = 1, email_verified_at = ?, updated_at = ? WHERE id = ?', (ts, ts, row['user_id']))
        session = _new_session(conn, int(row['user_id']))
        conn.commit()
        return True, 'Your email has been verified.', session


def login_user(email: str, password: str) -> tuple[bool, str, str]:
    email = email.strip().lower()
    with db() as conn:
        user = conn.execute('SELECT * FROM auth_users WHERE lower(email) = lower(?)', (email,)).fetchone()
        if not user or not verify_password(password, user['password_hash']):
            return False, 'Invalid email or password.', ''
        if not user['is_active']:
            return False, 'Verify your email before signing in.', ''
        session = _new_session(conn, int(user['id']))
        ts = now()
        conn.execute('UPDATE auth_users SET last_login_at = ?, updated_at = ? WHERE id = ?', (ts, ts, user['id']))
        conn.commit()
        return True, '', session


def logout_session(token: str) -> None:
    if not token:
        return
    with db() as conn:
        conn.execute('DELETE FROM auth_sessions WHERE token_hash = ?', (_token_hash(token),))
        conn.commit()


def current_user(session_token: str) -> sqlite3.Row | None:
    if not session_token:
        return None
    ts = now()
    with db() as conn:
        row = conn.execute(
            '''SELECT u.*, o.slug AS organization_slug, o.name AS organization_name
               FROM auth_sessions s
               JOIN auth_users u ON u.id = s.user_id
               JOIN auth_organizations o ON o.id = u.organization_id
               WHERE s.token_hash = ? AND s.expires_at >= ? AND u.is_active = 1''',
            (_token_hash(session_token), ts),
        ).fetchone()
        if row:
            conn.execute('UPDATE auth_sessions SET last_seen_at = ? WHERE token_hash = ?', (ts, _token_hash(session_token)))
            conn.commit()
        return row


def request_password_reset(email: str, organization_slug: str = '', public_host: str = '') -> None:
    email = email.strip().lower()
    organization_slug = organization_slug.strip().lower()
    if not organization_slug:
        return
    with db() as conn:
        user = conn.execute(
            '''SELECT u.* FROM auth_users u
               JOIN auth_organizations o ON o.id = u.organization_id
               WHERE lower(u.email) = lower(?) AND u.is_active = 1
                 AND o.slug = ? AND o.status = 'active' ''',
            (email, organization_slug),
        ).fetchone()
        if not user:
            return
        token = _new_token(conn, int(user['id']), 'reset_password', 60 * 60)
        conn.commit()
    reset_url = public_url(f'/reset-password/{quote(token)}', public_host)
    messaging.send_email(
        'Reset your Mad Mallard Platform password',
        f'Reset your password:\n{reset_url}\n\nThis link expires in one hour.',
        f'<p>Reset your password:</p><p><a href="{esc(reset_url)}">Choose a new password</a></p><p>This link expires in one hour.</p>',
        email,
    )


def reset_password(token: str, password: str) -> tuple[bool, str]:
    if len(password) < 12:
        return False, 'Password must be at least 12 characters.'
    ts = now()
    with db() as conn:
        row = conn.execute(
            '''SELECT id, user_id FROM auth_tokens
               WHERE token_hash = ? AND purpose = 'reset_password' AND used_at IS NULL AND expires_at >= ?''',
            (_token_hash(token), ts),
        ).fetchone()
        if not row:
            return False, 'This password-reset link is invalid or expired.'
        conn.execute('UPDATE auth_tokens SET used_at = ? WHERE id = ?', (ts, row['id']))
        conn.execute('UPDATE auth_users SET password_hash = ?, updated_at = ? WHERE id = ?', (hash_password(password), ts, row['user_id']))
        conn.execute('DELETE FROM auth_sessions WHERE user_id = ?', (row['user_id'],))
        conn.commit()
    return True, 'Your password has been changed.'


def session_cookie(token: str) -> str:
    return f'{SESSION_COOKIE}={token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age={SESSION_MAX_AGE}'


def clear_session_cookie() -> str:
    return f'{SESSION_COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0'


def page(title: str, content: str) -> str:
    return f'''<!doctype html><html><head><title>{esc(title)} - Mad Mallard Platform</title><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/assets/styles.css"></head><body class="conversation-page"><main class="conversation-shell">{content}</main></body></html>'''


def _customer_activity(user: sqlite3.Row) -> tuple[dict[str, int], list[sqlite3.Row]]:
    email = str(user['email']).strip().lower()
    tenant_slug = str(user['organization_slug']).strip().lower()
    tenant_conversations.ensure_schema()
    with db() as conn:
        counts_row = conn.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN status NOT IN ('closed', 'spam') THEN 1 ELSE 0 END) AS open_count,
                      SUM(CASE WHEN kind = 'project_request' THEN 1 ELSE 0 END) AS request_count,
                      SUM(CASE WHEN kind = 'chat' THEN 1 ELSE 0 END) AS conversation_count
               FROM conversations
               WHERE organization_slug = ?
                 AND lower(COALESCE(email, '')) = ?""",
            (tenant_slug, email),
        ).fetchone()
        recent = conn.execute(
            """SELECT token, kind, subject, status, updated_at
               FROM conversations
               WHERE organization_slug = ?
                 AND lower(COALESCE(email, '')) = ?
               ORDER BY updated_at DESC LIMIT 8""",
            (tenant_slug, email),
        ).fetchall()
    return {
        'total': int(counts_row['total'] or 0),
        'open': int(counts_row['open_count'] or 0),
        'requests': int(counts_row['request_count'] or 0),
        'conversations': int(counts_row['conversation_count'] or 0),
    }, recent


def _customer_history(
    user: sqlite3.Row,
    kind: str | None = None,
) -> list[sqlite3.Row]:
    return tenant_conversations.list_customer_conversations(
        str(user['organization_slug']),
        str(user['email']),
        kind,
    )


def _customer_conversation(
    user: sqlite3.Row,
    token: str,
) -> tuple[sqlite3.Row | None, list[sqlite3.Row]]:
    conversation = tenant_conversations.get_conversation(
        str(user['organization_slug']),
        token,
    )
    if not conversation or str(conversation['email'] or '').strip().lower() != str(user['email']).strip().lower():
        return None, []
    with db() as conn:
        messages = conn.execute(
            """SELECT *
               FROM messages
               WHERE conversation_id = ? AND internal = 0
               ORDER BY created_at ASC, id ASC""",
            (conversation['id'],),
        ).fetchall()
    return conversation, messages

def _fmt_timestamp(value: object) -> str:
    try:
        return time.strftime('%b %d, %Y %I:%M %p', time.localtime(int(value)))
    except (TypeError, ValueError, OSError):
        return ''


def render_customer_history(user: sqlite3.Row, kind: str) -> str:
    is_request = kind == 'project_request'
    title = 'My Requests' if is_request else 'My Conversations'
    empty = 'No service requests yet.' if is_request else 'No conversations yet.'
    records = _customer_history(user, kind)
    rows = ''.join(
        f'<article class="contact-panel">'
        f'<p><span class="badge status-{esc(row["status"])}">'
        f'{esc(row["status"]).replace("_", " ").title()}</span></p>'
        f'<h2>{esc(row["subject"] or ("Service request" if is_request else "Website chat"))}</h2>'
        f'<p class="muted">Updated {_fmt_timestamp(row["updated_at"])}</p>'
        f'<p><a class="btn secondary" href="/account/conversations/{esc(row["token"])}">Open</a></p>'
        f'</article>'
        for row in records
    ) or f'<section class="contact-panel"><p>{empty}</p></section>'

    other_href = '/conversations' if is_request else '/requests'
    other_label = 'My Conversations' if is_request else 'My Requests'
    return page(
        title,
        f'<p><a href="/dashboard">← Dashboard</a> · '
        f'<a href="{other_href}">{other_label}</a> · '
        f'<a href="/logout">Sign out</a></p>'
        f'<h1>{title}</h1>'
        f'<p>Activity associated with {esc(user["email"])}.</p>'
        f'<section class="inbox-list">{rows}</section>',
    )


def render_customer_conversation(user: sqlite3.Row, token: str) -> str | None:
    conversation, messages = _customer_conversation(user, token)
    if not conversation:
        return None

    rows = ''.join(
        f'<div class="msg {esc(message["sender_type"])}">'
        f'<div class="msg-meta"><strong>{esc(message["sender"])}</strong>'
        f'<span>{_fmt_timestamp(message["created_at"])}</span></div>'
        f'<p>{esc(message["body"])}</p></div>'
        for message in messages
    ) or '<p>No messages are available.</p>'

    is_request = conversation['kind'] == 'project_request'
    back_href = '/requests' if is_request else '/conversations'
    back_label = 'My Requests' if is_request else 'My Conversations'
    subject = conversation['subject'] or ('Service request' if is_request else 'Website chat')

    return page(
        subject,
        f'<p><a href="{back_href}">← {back_label}</a> · '
        f'<a href="/dashboard">Dashboard</a> · '
        f'<a href="/logout">Sign out</a></p>'
        f'<div class="thread-header"><div><h1>{esc(subject)}</h1>'
        f'<p class="muted">Created {_fmt_timestamp(conversation["created_at"])}'
        f' · Updated {_fmt_timestamp(conversation["updated_at"])}</p></div>'
        f'<span class="badge status-{esc(conversation["status"])}">'
        f'{esc(conversation["status"]).replace("_", " ").title()}</span></div>'
        f'<section class="message-list">{rows}</section>'
        f'<form id="customerReplyForm" class="contact-panel">'
        f'<label>Add a message<textarea name="body" rows="5" required></textarea></label>'
        f'<button class="btn primary" type="submit">Send message</button>'
        f'<p id="customerReplyStatus" class="form-status"></p></form>'
        f'<script>document.getElementById("customerReplyForm").addEventListener'
        f'("submit",async e=>{{e.preventDefault();const status=document.getElementById'
        f'("customerReplyStatus");status.textContent="Sending...";const body=e.target.body.value;'
        f'const r=await fetch("/api/chat/{esc(token)}/messages",{{method:"POST",headers:'
        f'{{"Content-Type":"application/json"}},body:JSON.stringify({{body}})}});'
        f'if(r.ok){{location.reload();}}else{{status.textContent="Message could not be sent.";}}}});'
        f'</script>',
    )


def update_profile(user_id: int, first_name: str, last_name: str, email: str) -> tuple[bool, str]:
    first_name, last_name, email = first_name.strip(), last_name.strip(), email.strip().lower()
    if not first_name or not last_name:
        return False, 'First and last name are required.'
    if not email or '@' not in email:
        return False, 'Enter a valid email address.'
    with db() as conn:
        duplicate = conn.execute('SELECT id FROM auth_users WHERE lower(email)=lower(?) AND id<>?', (email, user_id)).fetchone()
        if duplicate:
            return False, 'Another account already uses that email address.'
        conn.execute('UPDATE auth_users SET first_name=?, last_name=?, email=?, updated_at=? WHERE id=?', (first_name,last_name,email,now(),user_id))
        conn.commit()
    return True, 'Profile updated.'


def change_password(user_id: int, current_password: str, new_password: str) -> tuple[bool, str]:
    if len(new_password) < 12:
        return False, 'New password must be at least 12 characters.'
    with db() as conn:
        user = conn.execute('SELECT password_hash FROM auth_users WHERE id=?', (user_id,)).fetchone()
        if not user or not verify_password(current_password, user['password_hash']):
            return False, 'Current password is incorrect.'
        conn.execute('UPDATE auth_users SET password_hash=?, updated_at=? WHERE id=?', (hash_password(new_password), now(), user_id))
        conn.execute('DELETE FROM auth_sessions WHERE user_id=?', (user_id,))
        conn.commit()
    return True, 'Password changed. Sign in again with your new password.'


def render_profile(user: sqlite3.Row, message: str = '', error: bool = False) -> str:
    notice = f'<p class="{"error" if error else "muted"}">{esc(message)}</p>' if message else ''
    return page('Profile', f'''<p><a href="/dashboard">← Dashboard</a> · <a href="/logout">Sign out</a></p><h1>Profile</h1>{notice}<section class="contact-panel"><h2>Account details</h2><form method="post" action="/profile"><input type="hidden" name="action" value="profile"><label>First name<input name="first_name" value="{esc(user["first_name"])}" required></label><label>Last name<input name="last_name" value="{esc(user["last_name"])}" required></label><label>Email<input type="email" name="email" value="{esc(user["email"])}" required></label><button class="btn primary" type="submit">Save profile</button></form></section><section class="contact-panel"><h2>Change password</h2><p class="muted">Changing your password signs out every customer session.</p><form method="post" action="/profile"><input type="hidden" name="action" value="password"><label>Current password<input type="password" name="current_password" required></label><label>New password<input type="password" name="password" minlength="12" required></label><label>Confirm new password<input type="password" name="password_confirm" minlength="12" required></label><button class="btn primary" type="submit">Change password</button></form></section>''')


def render_register(message: str = '', error: bool = False) -> str:
    options = ''.join(f'<option value="{esc(o["slug"])}">{esc(o["name"])}</option>' for o in list_organizations())
    notice = f'<p class="{"error" if error else "muted"}">{esc(message)}</p>' if message else ''
    return page('Register', f'''<p><a href="/">← Site</a></p><h1>Create an account</h1><p>Register for the business you work with.</p>{notice}<form method="post" action="/register" class="contact-panel"><label>Business<select name="organization" required>{options}</select></label><label>First name<input name="first_name" required></label><label>Last name<input name="last_name" required></label><label>Email<input type="email" name="email" autocomplete="email" required></label><label>Password<input type="password" name="password" autocomplete="new-password" minlength="12" required></label><label>Confirm password<input type="password" name="password_confirm" autocomplete="new-password" minlength="12" required></label><button class="btn primary" type="submit">Create account</button></form><p>Already registered? <a href="/login">Sign in</a>.</p>''')


def render_login(message: str = '', error: bool = False) -> str:
    notice = f'<p class="{"error" if error else "muted"}">{esc(message)}</p>' if message else ''
    return page('Login', f'''<p><a href="/">← Site</a></p><h1>Sign in</h1>{notice}<form method="post" action="/login" class="contact-panel"><label>Email<input type="email" name="email" autocomplete="email" required autofocus></label><label>Password<input type="password" name="password" autocomplete="current-password" required></label><button class="btn primary" type="submit">Sign in</button></form><p><a href="/forgot-password">Forgot password?</a> · <a href="/register">Create account</a></p>''')


def render_forgot(message: str = '') -> str:
    notice = f'<p class="muted">{esc(message)}</p>' if message else ''
    return page('Forgot Password', f'''<p><a href="/login">← Sign in</a></p><h1>Reset your password</h1><p>Enter your email address. If an active account exists, we will send a reset link.</p>{notice}<form method="post" action="/forgot-password" class="contact-panel"><label>Email<input type="email" name="email" required autofocus></label><button class="btn primary" type="submit">Send reset link</button></form>''')


def render_reset(token: str, message: str = '', error: bool = False) -> str:
    notice = f'<p class="{"error" if error else "muted"}">{esc(message)}</p>' if message else ''
    return page('Reset Password', f'''<h1>Choose a new password</h1>{notice}<form method="post" action="/reset-password/{esc(token)}" class="contact-panel"><label>New password<input type="password" name="password" minlength="12" required autofocus></label><label>Confirm password<input type="password" name="password_confirm" minlength="12" required></label><button class="btn primary" type="submit">Change password</button></form>''')


def render_dashboard(user: sqlite3.Row) -> str:
    counts, recent = _customer_activity(user)
    rows = ''.join(
        f'<li><a href="/account/conversations/{esc(row["token"])}"><strong>'
        f'{esc(row["subject"] or ("Service request" if row["kind"] == "project_request" else "Website chat"))}'
        f'</strong></a><br><small>'
        f'{esc(row["status"]).replace("_", " ").title()}</small></li>'
        for row in recent
    ) or '<li>No customer activity yet.</li>'
    return page(
        'Dashboard',
        f'<p><a href="/">← Site</a> · <a href="/profile">Profile</a> · '
        f'<a href="/logout">Sign out</a></p>'
        f'<h1>Welcome, {esc(user["first_name"])}</h1>'
        f'<p>Your account is active for <strong>{esc(user["organization_name"])}</strong>.</p>'
        f'<section class="dashboard-grid">'
        f'<a class="dash-card" href="/requests"><span>Requests</span><strong>{counts["requests"]}</strong></a>'
        f'<a class="dash-card" href="/conversations"><span>Conversations</span><strong>{counts["conversations"]}</strong></a>'
        f'<article class="dash-card"><span>Open</span><strong>{counts["open"]}</strong></article>'
        f'<article class="dash-card"><span>Total activity</span><strong>{counts["total"]}</strong></article>'
        f'</section>'
        f'<section class="contact-panel"><h2>Recent activity</h2><ul>{rows}</ul>'
        f'<p><a href="/requests">View all requests</a> · '
        f'<a href="/conversations">View all conversations</a></p></section>'
        f'<section class="contact-panel"><h2>Account</h2>'
        f'<p><strong>Email:</strong> {esc(user["email"])}</p>'
        f'<p><strong>Role:</strong> {esc(user["role"]).title()}</p>'
        f'<p><strong>Business:</strong> {esc(user["organization_name"])}</p>'
        f'<p><a class="btn secondary" href="/profile">Manage profile</a></p></section>',
    )
