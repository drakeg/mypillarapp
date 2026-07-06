from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, parse_qs, urlparse
import html
import json
import mimetypes
import os
import secrets
import http.cookies
import messaging

ROOT = Path('/app').resolve()
INDEX = ROOT / 'index.html'
ADMIN_TOKEN = os.environ.get('MADMALLARD_ADMIN_TOKEN', '').strip()
PRIMARY_DOMAIN = os.environ.get('MADMALLARD_PRIMARY_DOMAIN', 'pillar.madmallards.com')

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


def read_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get('Content-Length', '0') or '0')
    raw = handler.rfile.read(length) if length else b''
    ctype = handler.headers.get('Content-Type', '')
    if 'application/x-www-form-urlencoded' in ctype:
        parsed = parse_qs(raw.decode('utf-8'))
        return {k: v[0] if v else '' for k, v in parsed.items()}
    try:
        return json.loads(raw.decode('utf-8') or '{}')
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
    supplied = query.get('token', [''])[0] if query else ''
    cookie_token = get_cookie(handler, 'mms_admin')
    return secrets.compare_digest(supplied, ADMIN_TOKEN) or secrets.compare_digest(cookie_token, ADMIN_TOKEN)


def require_admin(handler: BaseHTTPRequestHandler, query: dict | None = None) -> bool:
    if not ADMIN_TOKEN:
        html_response(handler, 403, '<h1>Admin disabled</h1><p>Set admin_token in Terraform to enable the inbox.</p>')
        return False
    if not admin_is_authenticated(handler, query):
        redirect(handler, '/admin/login')
        return False
    return True


def esc(value) -> str:
    return html.escape(str(value or ''))


class Handler(BaseHTTPRequestHandler):
    server_version = 'MadMallardPlatform/0.3'

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
            return self.render_chat(path.rstrip('/').split('/')[-1])
        if path == '/admin/login':
            return self.render_login()
        if path == '/admin/logout':
            return html_response(self, 200, '<h1>Signed out</h1><p><a href="/admin/login">Sign in again</a></p>', {'Set-Cookie': 'mms_admin=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax'})
        if path == '/admin/inbox':
            if not require_admin(self, query):
                return
            return self.render_inbox()
        if path.startswith('/admin/conversations/'):
            if not require_admin(self, query):
                return
            return self.render_admin_conversation(path.rstrip('/').split('/')[-1])

        file_path = self._resolve_path()
        if file_path and file_path.exists():
            return self._send_file(file_path, 'text/html; charset=utf-8' if file_path == INDEX else None)
        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        payload = read_body(self)

        if parsed.path == '/admin/login':
            token = str(payload.get('token', '')).strip()
            if ADMIN_TOKEN and secrets.compare_digest(token, ADMIN_TOKEN):
                return redirect(self, '/admin/inbox', {'Set-Cookie': f'mms_admin={ADMIN_TOKEN}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000'})
            return html_response(self, 403, '<h1>Invalid token</h1><p><a href="/admin/login">Try again</a></p>')

        if parsed.path == '/api/contact':
            return self.handle_project_request(payload)
        if parsed.path == '/api/chat/start':
            return self.handle_chat_start(payload)
        if parsed.path.startswith('/api/chat/') and parsed.path.endswith('/messages'):
            token = parsed.path.split('/')[3]
            return self.handle_visitor_message(token, payload)
        if parsed.path.startswith('/api/admin/conversations/') and parsed.path.endswith('/messages'):
            query = parse_qs(parsed.query)
            if not require_admin(self, query):
                return
            token = parsed.path.split('/')[3]
            return self.handle_admin_message(token, payload)
        if parsed.path.startswith('/api/admin/conversations/') and parsed.path.endswith('/update'):
            query = parse_qs(parsed.query)
            if not require_admin(self, query):
                return
            token = parsed.path.split('/')[3]
            return self.handle_admin_update(token, payload)

        self.send_error(404)

    def handle_project_request(self, payload: dict):
        if payload.get('website'):
            return json_response(self, 200, {'ok': True})
        name = str(payload.get('name', '')).strip()
        email = str(payload.get('email', '')).strip()
        company = str(payload.get('company', '')).strip()
        service = str(payload.get('service', '')).strip()
        timeline = str(payload.get('timeline', '')).strip()
        budget = str(payload.get('budget', '')).strip()
        message = str(payload.get('message', '')).strip()
        if not name or not email or not message:
            return json_response(self, 400, {'ok': False, 'error': 'Name, email, and message are required.'})
        subject = service or 'Project request'
        body = f"Service: {service}\nTimeline: {timeline}\nBudget: {budget}\n\n{message}"
        convo = messaging.create_conversation(
            kind='project_request', name=name, email=email, company=company, subject=subject,
            body=body, tags=[service] if service else [], lead={'service': service, 'timeline': timeline, 'budget': budget, 'message': message},
        )
        messaging.notify_new_conversation(convo, body)
        messaging.notify_visitor_link(convo)
        return json_response(self, 200, {'ok': True, 'message': 'Thanks. Your request was saved.', 'conversation_url': f'/chat/{convo["token"]}'})

    def handle_chat_start(self, payload: dict):
        name = str(payload.get('name', '')).strip() or 'Visitor'
        email = str(payload.get('email', '')).strip()
        body = str(payload.get('body', '')).strip()
        if not body:
            return json_response(self, 400, {'ok': False, 'error': 'Please enter a message.'})
        convo = messaging.create_conversation(kind='chat', name=name, email=email, subject='Website chat', body=body, tags=['chat'])
        messaging.notify_new_conversation(convo, body)
        messaging.notify_visitor_link(convo)
        return json_response(self, 200, {'ok': True, 'url': f'/chat/{convo["token"]}', 'full_url': messaging.public_url(f'/chat/{convo["token"]}')})

    def handle_visitor_message(self, token: str, payload: dict):
        body = str(payload.get('body', '')).strip()
        sender = str(payload.get('sender', 'Visitor')).strip() or 'Visitor'
        if not body:
            return json_response(self, 400, {'ok': False, 'error': 'Message is required.'})
        convo = messaging.add_message(token, body=body, sender=sender, sender_type='visitor')
        if not convo:
            return json_response(self, 404, {'ok': False, 'error': 'Conversation not found.'})
        messaging.notify_admin_reply(convo, sender, body)
        return json_response(self, 200, {'ok': True})

    def handle_admin_message(self, token: str, payload: dict):
        body = str(payload.get('body', '')).strip()
        internal = str(payload.get('internal', '')).lower() in ['1', 'true', 'yes', 'on']
        if not body:
            return json_response(self, 400, {'ok': False, 'error': 'Message is required.'})
        convo = messaging.add_message(token, body=body, sender='Greg', sender_type='admin', internal=internal)
        if not convo:
            return json_response(self, 404, {'ok': False, 'error': 'Conversation not found.'})
        if not internal:
            messaging.notify_visitor_admin_reply(convo, body)
        return json_response(self, 200, {'ok': True})

    def handle_admin_update(self, token: str, payload: dict):
        ok = messaging.update_conversation(token, status=payload.get('status'), priority=payload.get('priority'), tags=payload.get('tags'))
        return json_response(self, 200 if ok else 400, {'ok': ok})

    def render_login(self):
        body = """<!doctype html><html><head><title>Admin Login - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head>
<body class='conversation-page'><main class='conversation-shell'><h1>Admin login</h1><p>Enter the admin token once. This browser will remember it for 30 days.</p><form method='post' action='/admin/login' class='contact-panel'><label>Admin token<input type='password' name='token' autocomplete='current-password' required autofocus></label><button class='btn primary' type='submit'>Open inbox</button></form></main></body></html>"""
        return html_response(self, 200, body)

    def render_chat(self, token: str):
        convo, messages = messaging.get_conversation(token)
        if not convo:
            return html_response(self, 404, '<h1>Conversation not found</h1>')
        visible = [m for m in messages if not m['internal']]
        rows = ''.join(f"<div class='msg {esc(m['sender_type'])}'><strong>{esc(m['sender'])}</strong><p>{esc(m['body'])}</p></div>" for m in visible)
        body = f"""<!doctype html><html><head><title>Conversation - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head>
<body class='conversation-page'><main class='conversation-shell'><a href='/'>← Back</a><h1>Conversation</h1><p>This private link lets you continue the conversation with Mad Mallard Solutions.</p><section class='message-list'>{rows}</section><form id='replyForm' class='contact-panel'><textarea name='body' rows='5' placeholder='Add a message...' required></textarea><button class='btn primary' type='submit'>Send message</button></form></main><script>document.getElementById('replyForm').addEventListener('submit', async e=>{{e.preventDefault(); const body=e.target.body.value; const r=await fetch('/api/chat/{token}/messages',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{body}})}}); if(r.ok) location.reload();}});</script></body></html>"""
        return html_response(self, 200, body)

    def render_inbox(self):
        convos = messaging.list_conversations()
        rows = []
        for c in convos:
            rows.append(f"<tr><td><a href='/admin/conversations/{esc(c['token'])}'>{esc(c['name'] or 'Visitor')}</a><br><small>{esc(c['email'])}</small></td><td>{esc(c['kind'])}</td><td><span class='badge status-{esc(c['status'])}'>{esc(c['status'])}</span></td><td>{esc(c['priority'])}</td><td>{esc(c['tags'])}</td></tr>")
        table = ''.join(rows) or '<tr><td colspan="5">No conversations yet.</td></tr>'
        body = f"""<!doctype html><html><head><title>Inbox - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head><body class='conversation-page'><main class='conversation-shell wide'><p><a href='/'>← Site</a> · <a href='/admin/logout'>Sign out</a></p><h1>Mad Mallard Inbox</h1><table class='inbox-table'><thead><tr><th>Contact</th><th>Type</th><th>Status</th><th>Priority</th><th>Tags</th></tr></thead><tbody>{table}</tbody></table></main></body></html>"""
        return html_response(self, 200, body)

    def render_admin_conversation(self, token: str):
        convo, messages = messaging.get_conversation(token)
        if not convo:
            return html_response(self, 404, '<h1>Conversation not found</h1>')
        rows = ''.join(f"<div class='msg {esc(m['sender_type'])}{' internal' if m['internal'] else ''}'><strong>{esc(m['sender'])}{' · internal note' if m['internal'] else ''}</strong><p>{esc(m['body'])}</p></div>" for m in messages)
        status_opts = ''.join(f"<option value='{s}' {'selected' if convo['status']==s else ''}>{s}</option>" for s in messaging.STATUSES)
        pri_opts = ''.join(f"<option value='{p}' {'selected' if convo['priority']==p else ''}>{p}</option>" for p in messaging.PRIORITIES)
        body = f"""<!doctype html><html><head><title>Conversation Admin - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head><body class='conversation-page'><main class='conversation-shell'><p><a href='/admin/inbox'>← Inbox</a></p><h1>{esc(convo['subject'] or 'Conversation')}</h1><p><strong>{esc(convo['name'])}</strong> · {esc(convo['email'])} · {esc(convo['company'])}</p><form id='metaForm' class='contact-panel compact'><label>Status<select name='status'>{status_opts}</select></label><label>Priority<select name='priority'>{pri_opts}</select></label><label>Tags<input name='tags' value='{esc(convo['tags'])}'></label><button class='btn secondary' type='submit'>Save</button></form><section class='message-list'>{rows}</section><form id='replyForm' class='contact-panel'><textarea name='body' rows='5' placeholder='Reply to visitor or add internal note...' required></textarea><label class='check'><input type='checkbox' name='internal'> Internal note only</label><button class='btn primary' type='submit'>Send</button></form></main><script>document.getElementById('replyForm').addEventListener('submit', async e=>{{e.preventDefault(); const fd=new FormData(e.target); const data=Object.fromEntries(fd.entries()); data.internal=e.target.internal.checked; const r=await fetch('/api/admin/conversations/{token}/messages',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}}); if(r.ok) location.reload();}});document.getElementById('metaForm').addEventListener('submit', async e=>{{e.preventDefault(); const data=Object.fromEntries(new FormData(e.target).entries()); const r=await fetch('/api/admin/conversations/{token}/update',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}}); if(r.ok) location.reload();}});</script></body></html>"""
        return html_response(self, 200, body)


if __name__ == '__main__':
    messaging.db()
    print(f'Mad Mallard Platform serving {PRIMARY_DOMAIN} on :8000', flush=True)
    ThreadingHTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
