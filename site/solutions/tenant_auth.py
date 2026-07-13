from __future__ import annotations

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


def public_url(path: str) -> str:
    if not path.startswith('/'):
        path = '/' + path
    return f'https://{PRIMARY_DOMAIN}{path}'


def db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    ensure_schema(conn)
    return conn


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


def register_user(*, organization_slug: str, first_name: str, last_name: str, email: str, password: str) -> tuple[bool, str]:
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
    verify_url = public_url(f'/verify-email/{quote(token)}')
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


def request_password_reset(email: str) -> None:
    email = email.strip().lower()
    with db() as conn:
        user = conn.execute('SELECT * FROM auth_users WHERE lower(email) = lower(?) AND is_active = 1', (email,)).fetchone()
        if not user:
            return
        token = _new_token(conn, int(user['id']), 'reset_password', 60 * 60)
        conn.commit()
    reset_url = public_url(f'/reset-password/{quote(token)}')
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
    return page('Dashboard', f'''<p><a href="/">← Site</a> · <a href="/logout">Sign out</a></p><h1>Welcome, {esc(user["first_name"])}</h1><p>Your account is active for <strong>{esc(user["organization_name"])}</strong>.</p><section class="contact-panel"><p><strong>Email:</strong> {esc(user["email"])}</p><p><strong>Role:</strong> {esc(user["role"]).title()}</p><p><strong>Business:</strong> {esc(user["organization_name"])}</p></section><p>This is the Sprint 1 account dashboard foundation. No admin routes or admin UI are shared with this account.</p>''')
