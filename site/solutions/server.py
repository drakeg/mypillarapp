from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, parse_qs, urlparse
import html
import json
import mimetypes
import os
import secrets
import sqlite3
import time
import http.cookies

ROOT = Path('/app').resolve()
DATA_DIR = Path('/data')
DB_PATH = DATA_DIR / 'madmallard.sqlite3'
INDEX = ROOT / 'index.html'
ADMIN_TOKEN = os.environ.get('MADMALLARD_ADMIN_TOKEN', '').strip()
PRIMARY_DOMAIN = os.environ.get('MADMALLARD_PRIMARY_DOMAIN', 'pillar.madmallards.com')
ENABLE_EMAIL = os.environ.get('MADMALLARD_ENABLE_EMAIL', 'false').strip().lower() == 'true'
NOTIFY_FROM = os.environ.get('MADMALLARD_NOTIFY_FROM', '').strip()
NOTIFY_TO = os.environ.get('MADMALLARD_NOTIFY_TO', '').strip()
AWS_REGION = os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')).strip()

FORM_CONFIG = {
    'services': [
        'AWS / cloud setup',
        'Linux server support',
        'Terraform / infrastructure as code',
        'Docker / deployment help',
        'Automation / scripting',
        'Small business website',
        'Not sure yet',
    ],
    'timelines': ['ASAP', 'This week', 'This month', 'Just exploring'],
    'budgets': ['Not sure yet', 'Under $500', '$500 - $1,500', '$1,500 - $5,000', '$5,000+'],
}


def db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            name TEXT,
            email TEXT,
            status TEXT NOT NULL DEFAULT 'open'
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            sender TEXT NOT NULL,
            body TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id)
        )
    ''')
    conn.commit()
    return conn


def now() -> int:
    return int(time.time())


def public_url(path: str = '/') -> str:
    if not path.startswith('/'):
        path = '/' + path
    return f'https://{PRIMARY_DOMAIN}{path}'


def read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get('Content-Length', '0') or '0')
    raw = handler.rfile.read(length) if length else b'{}'
    ctype = handler.headers.get('Content-Type', '')
    if 'application/x-www-form-urlencoded' in ctype:
        parsed = parse_qs(raw.decode('utf-8'))
        return {k: v[0] if v else '' for k, v in parsed.items()}
    try:
        return json.loads(raw.decode('utf-8'))
    except json.JSONDecodeError:
        return {}


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict):
    body = json.dumps(payload).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    if handler.command != 'HEAD':
        handler.wfile.write(body)


def html_response(handler: BaseHTTPRequestHandler, status: int, body: str, headers: dict | None = None):
    data = body.encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'text/html; charset=utf-8')
    handler.send_header('Content-Length', str(len(data)))
    if headers:
        for key, value in headers.items():
            handler.send_header(key, value)
    handler.end_headers()
    if handler.command != 'HEAD':
        handler.wfile.write(data)


def redirect(handler: BaseHTTPRequestHandler, location: str, headers: dict | None = None):
    handler.send_response(303)
    handler.send_header('Location', location)
    if headers:
        for key, value in headers.items():
            handler.send_header(key, value)
    handler.end_headers()


def get_cookie(handler: BaseHTTPRequestHandler, name: str) -> str:
    raw = handler.headers.get('Cookie', '')
    cookie = http.cookies.SimpleCookie()
    try:
        cookie.load(raw)
    except http.cookies.CookieError:
        return ''
    return cookie.get(name).value if name in cookie else ''


def admin_is_authenticated(handler: BaseHTTPRequestHandler, query: dict | None = None) -> bool:
    if not ADMIN_TOKEN:
        return False
    supplied = ''
    if query:
        supplied = query.get('token', [''])[0]
    cookie_token = get_cookie(handler, 'mms_admin')
    return secrets.compare_digest(supplied, ADMIN_TOKEN) or secrets.compare_digest(cookie_token, ADMIN_TOKEN)


def require_admin(handler: BaseHTTPRequestHandler, query: dict | None = None) -> bool:
    if not ADMIN_TOKEN:
        html_response(handler, 403, '<h1>Admin disabled</h1><p>Set MADMALLARD_ADMIN_TOKEN to enable the inbox.</p>')
        return False
    if not admin_is_authenticated(handler, query):
        redirect(handler, '/admin/login')
        return False
    return True


def send_email(subject: str, text_body: str, html_body: str | None = None, to_address: str | None = None):
    if not ENABLE_EMAIL or not NOTIFY_FROM:
        return
    destination = to_address or NOTIFY_TO
    if not destination:
        return
    try:
        import boto3  # installed in container at service startup when email is enabled
        client = boto3.client('sesv2', region_name=AWS_REGION)
        body = {'Text': {'Data': text_body, 'Charset': 'UTF-8'}}
        if html_body:
            body['Html'] = {'Data': html_body, 'Charset': 'UTF-8'}
        client.send_email(
            FromEmailAddress=NOTIFY_FROM,
            Destination={'ToAddresses': [destination]},
            Content={'Simple': {'Subject': {'Data': subject, 'Charset': 'UTF-8'}, 'Body': body}},
        )
    except Exception as exc:
        print(f'Email notification failed: {exc}', flush=True)


def notify_admin(subject: str, body: str):
    inbox_link = public_url('/admin/inbox')
    send_email(subject, f'{body}\n\nAdmin inbox: {inbox_link}', f'<p>{html.escape(body)}</p><p><a href="{inbox_link}">Open admin inbox</a></p>')


def notify_visitor_conversation(email: str, name: str, url: str):
    if not email:
        return
    send_email(
        'Your Mad Mallard Solutions conversation link',
        f'Hi {name or "there"},\n\nYour private conversation link is:\n{url}\n\nYou can bookmark this link or return to it from this email.',
        f'<p>Hi {html.escape(name or "there")},</p><p>Your private conversation link is:</p><p><a href="{url}">{url}</a></p><p>You can bookmark this link or return to it from this email.</p>',
        to_address=email,
    )


class Handler(BaseHTTPRequestHandler):
    server_version = 'MadMallardPlatform/0.2'

    def log_message(self, fmt, *args):
        print('%s - - [%s] %s' % (self.client_address[0], self.log_date_time_string(), fmt % args), flush=True)

    def _send_file(self, path: Path, content_type: str | None = None):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', content_type or mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-cache' if path.suffix == '.html' else 'public, max-age=3600')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def _resolve_path(self):
        requested = unquote(urlparse(self.path).path).lstrip('/')
        if requested == '' or requested.endswith('/'):
            return INDEX
        candidate = (ROOT / requested).resolve()
        if not str(candidate).startswith(str(ROOT)):
            return None
        return candidate if candidate.is_file() else INDEX

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == '/api/form-config':
            return json_response(self, 200, FORM_CONFIG)

        if path.startswith('/chat/'):
            token = path.rstrip('/').split('/')[-1]
            return self.render_chat(token)

        if path == '/admin/login':
            return self.render_login()

        if path == '/admin/logout':
            return html_response(self, 200, '<h1>Signed out</h1><p><a href="/admin/login">Sign in again</a></p>', {'Set-Cookie': 'mms_admin=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax'})

        if path == '/admin/inbox':
            if not require_admin(self, query):
                return
            return self.render_inbox()

        file_path = self._resolve_path()
        if file_path and file_path.exists():
            return self._send_file(file_path, 'text/html; charset=utf-8' if file_path == INDEX else None)
        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        payload = read_json(self)

        if parsed.path == '/admin/login':
            token = str(payload.get('token', '')).strip()
            if ADMIN_TOKEN and secrets.compare_digest(token, ADMIN_TOKEN):
                return redirect(self, '/admin/inbox', {'Set-Cookie': f'mms_admin={ADMIN_TOKEN}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000'})
            return html_response(self, 403, '<h1>Invalid token</h1><p><a href="/admin/login">Try again</a></p>')

        if parsed.path == '/api/contact':
            return self.create_lead(payload)
        if parsed.path == '/api/chat/start':
            return self.start_chat(payload)
        if parsed.path.startswith('/api/chat/') and parsed.path.endswith('/messages'):
            token = parsed.path.split('/')[3]
            return self.add_message(token, payload)
        if parsed.path.startswith('/api/admin/chat/') and parsed.path.endswith('/reply'):
            token = parsed.path.split('/')[4]
            query = parse_qs(parsed.query)
            if not require_admin(self, query):
                return
            return self.add_message(token, {'body': payload.get('body', ''), 'sender': 'Greg'}, admin_reply=True)
        return self.send_error(404)

    def create_lead(self, payload: dict):
        if payload.get('website'):
            return json_response(self, 200, {'ok': True})
        name = str(payload.get('name', '')).strip()
        email = str(payload.get('email', '')).strip()
        message = str(payload.get('message', '')).strip()
        if not name or not email or not message:
            return json_response(self, 400, {'ok': False, 'error': 'Name, email, and message are required.'})
        fields = {k: v for k, v in payload.items() if k != 'website'}
        with db() as conn:
            cur = conn.execute(
                'INSERT INTO leads(created_at, name, email, company, source, fields_json) VALUES (?, ?, ?, ?, ?, ?)',
                (now(), name, email, str(payload.get('company', '')).strip(), 'contact_form', json.dumps(fields)),
            )
            lead_id = cur.lastrowid
            conn.commit()
        notify_admin('New Mad Mallard Solutions project request', f'New project request #{lead_id} from {name} <{email}>.\n\n{message}')
        return json_response(self, 200, {'ok': True, 'message': 'Thanks. Your project request was saved.'})

    def start_chat(self, payload: dict):
        name = str(payload.get('name', '')).strip() or 'Visitor'
        email = str(payload.get('email', '')).strip()
        body = str(payload.get('body', '')).strip()
        if not body:
            return json_response(self, 400, {'ok': False, 'error': 'Please enter a message.'})
        token = secrets.token_urlsafe(18)
        ts = now()
        with db() as conn:
            cur = conn.execute(
                'INSERT INTO conversations(created_at, updated_at, token, name, email) VALUES (?, ?, ?, ?, ?)',
                (ts, ts, token, name, email),
            )
            conversation_id = cur.lastrowid
            conn.execute(
                'INSERT INTO messages(conversation_id, created_at, sender, body) VALUES (?, ?, ?, ?)',
                (conversation_id, ts, name, body),
            )
            conn.commit()
        url = public_url(f'/chat/{token}')
        notify_admin('New Mad Mallard Solutions chat message', f'New chat from {name} <{email or "no email"}>.\n\n{body}\n\nConversation: {url}')
        notify_visitor_conversation(email, name, url)
        return json_response(self, 200, {'ok': True, 'token': token, 'url': f'/chat/{token}', 'full_url': url, 'emailed': bool(email and ENABLE_EMAIL and NOTIFY_FROM)})

    def add_message(self, token: str, payload: dict, admin_reply: bool = False):
        body = str(payload.get('body', '')).strip()
        sender = str(payload.get('sender', 'Visitor')).strip() or 'Visitor'
        if not body:
            return json_response(self, 400, {'ok': False, 'error': 'Message is required.'})
        with db() as conn:
            convo = conn.execute('SELECT * FROM conversations WHERE token = ?', (token,)).fetchone()
            if not convo:
                return json_response(self, 404, {'ok': False, 'error': 'Conversation not found.'})
            ts = now()
            conn.execute('INSERT INTO messages(conversation_id, created_at, sender, body) VALUES (?, ?, ?, ?)', (convo['id'], ts, sender, body))
            conn.execute('UPDATE conversations SET updated_at = ? WHERE id = ?', (ts, convo['id']))
            conn.commit()
        convo_url = public_url(f'/chat/{token}')
        if admin_reply and convo['email']:
            send_email('Greg replied to your Mad Mallard Solutions conversation', f'Greg replied:\n\n{body}\n\nOpen conversation: {convo_url}', f'<p>Greg replied:</p><blockquote>{html.escape(body)}</blockquote><p><a href="{convo_url}">Open conversation</a></p>', to_address=convo['email'])
        elif not admin_reply:
            notify_admin('New reply in Mad Mallard Solutions chat', f'{sender} replied:\n\n{body}\n\nConversation: {convo_url}')
        return json_response(self, 200, {'ok': True})

    def render_login(self):
        body = """<!doctype html><html><head><title>Admin Login - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head>
<body class='conversation-page'><main class='conversation-shell'><h1>Admin login</h1><p>Enter the admin token once. This browser will remember it for 30 days.</p><form method='post' action='/admin/login' class='contact-panel'><label>Admin token<input type='password' name='token' autocomplete='current-password' required autofocus></label><button class='btn primary' type='submit'>Open inbox</button></form></main></body></html>"""
        return html_response(self, 200, body)

    def render_chat(self, token: str):
        with db() as conn:
            convo = conn.execute('SELECT * FROM conversations WHERE token = ?', (token,)).fetchone()
            if not convo:
                return html_response(self, 404, '<h1>Conversation not found</h1>')
            messages = conn.execute('SELECT * FROM messages WHERE conversation_id = ? ORDER BY id', (convo['id'],)).fetchall()
        rows = ''.join(
            f"<div class='msg'><strong>{html.escape(m['sender'])}</strong><p>{html.escape(m['body'])}</p></div>" for m in messages
        )
        body = f"""<!doctype html><html><head><title>Conversation - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head>
<body class='conversation-page'><main class='conversation-shell'><a href='/'>← Back</a><h1>Conversation</h1><p>This is your private conversation page. If you entered an email address, a copy of this link was sent to you.</p><section class='message-list'>{rows}</section><form id='replyForm' class='contact-panel'><textarea name='body' rows='5' placeholder='Add a message...' required></textarea><button class='btn primary' type='submit'>Send message</button></form></main><script>document.getElementById('replyForm').addEventListener('submit', async e=>{{e.preventDefault(); const body=e.target.body.value; const r=await fetch('/api/chat/{token}/messages',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{body}})}}); if(r.ok) location.reload();}});</script></body></html>"""
        return html_response(self, 200, body)

    def render_inbox(self):
        with db() as conn:
            leads = conn.execute('SELECT * FROM leads ORDER BY id DESC LIMIT 50').fetchall()
            convos = conn.execute('SELECT * FROM conversations ORDER BY updated_at DESC LIMIT 50').fetchall()
        lead_rows = ''.join(f"<li><strong>{html.escape(l['name'] or '')}</strong> &lt;{html.escape(l['email'] or '')}&gt;<br><small>{html.escape(l['fields_json'])}</small></li>" for l in leads)
        convo_rows = ''.join(f"<li><a href='/chat/{html.escape(c['token'])}'>{html.escape(c['name'] or 'Visitor')}</a> &lt;{html.escape(c['email'] or '')}&gt;</li>" for c in convos)
        body = f"""<!doctype html><html><head><title>Inbox - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head><body class='conversation-page'><main class='conversation-shell'><p><a href='/'>← Site</a> · <a href='/admin/logout'>Sign out</a></p><h1>Mad Mallard Inbox</h1><h2>Leads</h2><ul>{lead_rows or '<li>No leads yet.</li>'}</ul><h2>Conversations</h2><ul>{convo_rows or '<li>No conversations yet.</li>'}</ul><p><small>Admin session is stored in a secure browser cookie.</small></p></main></body></html>"""
        return html_response(self, 200, body)


if __name__ == '__main__':
    db()
    print(f'Mad Mallard Platform serving {PRIMARY_DOMAIN} on :8000', flush=True)
    ThreadingHTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
