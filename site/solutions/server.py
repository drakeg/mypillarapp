from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, parse_qs, urlparse
import html
import hmac
import hashlib
import base64
import json
import mimetypes
import os
import secrets
import http.cookies
import messaging
import platform_core

ROOT = Path('/app').resolve()
INDEX = ROOT / 'index.html'
ADMIN_TOKEN = os.environ.get('MADMALLARD_ADMIN_TOKEN', '').strip()  # legacy fallback
ADMIN_USERNAME = os.environ.get('MADMALLARD_ADMIN_USERNAME', 'greg').strip()
ADMIN_PASSWORD_HASH = os.environ.get('MADMALLARD_ADMIN_PASSWORD_HASH', '').strip()
ADMIN_SESSION_SECRET = os.environ.get('MADMALLARD_ADMIN_SESSION_SECRET', ADMIN_PASSWORD_HASH or ADMIN_TOKEN or 'dev-only-change-me').strip()
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
        return {k: (v if len(v) > 1 else (v[0] if v else '')) for k, v in parsed.items()}
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


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def _unb64url(value: str) -> bytes:
    padding = '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode('ascii'))


def make_admin_session(username: str) -> str:
    payload = json.dumps({'u': username, 'exp': messaging.now() + 60 * 60 * 24 * 30}, separators=(',', ':')).encode('utf-8')
    encoded = _b64url(payload)
    sig = hmac.new(ADMIN_SESSION_SECRET.encode('utf-8'), encoded.encode('ascii'), hashlib.sha256).digest()
    return f'{encoded}.{_b64url(sig)}'


def verify_admin_session(value: str) -> bool:
    if not value or '.' not in value:
        return False
    encoded, supplied_sig = value.split('.', 1)
    expected = _b64url(hmac.new(ADMIN_SESSION_SECRET.encode('utf-8'), encoded.encode('ascii'), hashlib.sha256).digest())
    if not hmac.compare_digest(supplied_sig, expected):
        return False
    try:
        payload = json.loads(_unb64url(encoded))
    except Exception:
        return False
    return payload.get('u') == ADMIN_USERNAME and int(payload.get('exp', 0)) > messaging.now()


def verify_password(password: str) -> bool:
    """Verify pbkdf2_sha256$iterations$salt$hash admin passwords."""
    if not ADMIN_PASSWORD_HASH:
        return False
    try:
        algorithm, iterations, salt, stored = ADMIN_PASSWORD_HASH.split('$', 3)
        if algorithm != 'pbkdf2_sha256':
            return False
        digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), int(iterations))
        calculated = _b64url(digest)
        return hmac.compare_digest(calculated, stored)
    except Exception as exc:
        print(f'Admin password verification failed: {exc}', flush=True)
        return False


def admin_auth_enabled() -> bool:
    return bool(ADMIN_PASSWORD_HASH or ADMIN_TOKEN)


def admin_is_authenticated(handler: BaseHTTPRequestHandler, query: dict | None = None) -> bool:
    if not admin_auth_enabled():
        return False
    session = get_cookie(handler, 'mms_admin_session')
    if verify_admin_session(session):
        return True
    # Legacy support so existing bookmarked token URLs still work while migrating.
    supplied = query.get('token', [''])[0] if query else ''
    return bool(ADMIN_TOKEN and secrets.compare_digest(supplied, ADMIN_TOKEN))


def require_admin(handler: BaseHTTPRequestHandler, query: dict | None = None) -> bool:
    if not admin_auth_enabled():
        html_response(handler, 403, '<h1>Admin disabled</h1><p>Set admin_username and admin_password_hash in Terraform to enable the inbox.</p>')
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
            return html_response(self, 200, '<h1>Signed out</h1><p><a href="/admin/login">Sign in again</a></p>', {'Set-Cookie': 'mms_admin_session=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax'})
        if path == '/admin/dashboard' or path == '/admin':
            if not require_admin(self, query):
                return
            return self.render_dashboard()
        if path == '/admin/organizations':
            if not require_admin(self, query):
                return
            return self.render_organizations()
        if path.startswith('/admin/organizations/'):
            if not require_admin(self, query):
                return
            return self.render_organization_detail(path.rstrip('/').split('/')[-1])
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
            username = str(payload.get('username', '')).strip()
            password = str(payload.get('password', '')).strip()
            token = str(payload.get('token', '')).strip()
            if ADMIN_PASSWORD_HASH and username == ADMIN_USERNAME and verify_password(password):
                cookie = make_admin_session(username)
                return redirect(self, '/admin/dashboard', {'Set-Cookie': f'mms_admin_session={cookie}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000'})
            if not ADMIN_PASSWORD_HASH and ADMIN_TOKEN and secrets.compare_digest(token, ADMIN_TOKEN):
                cookie = make_admin_session(ADMIN_USERNAME or 'admin')
                return redirect(self, '/admin/dashboard', {'Set-Cookie': f'mms_admin_session={cookie}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000'})
            return html_response(self, 403, '<h1>Invalid login</h1><p><a href="/admin/login">Try again</a></p>')

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
        if parsed.path.startswith('/admin/organizations/') and parsed.path.endswith('/save'):
            query = parse_qs(parsed.query)
            if not require_admin(self, query):
                return
            slug = parsed.path.strip('/').split('/')[2]
            return self.handle_organization_save(slug, payload)

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


    def admin_shell(self, title: str, content: str, active: str = 'dashboard'):
        nav = [
            ('dashboard', '/admin/dashboard', 'Dashboard'),
            ('organizations', '/admin/organizations', 'Organizations'),
            ('inbox', '/admin/inbox', 'Inbox'),
            ('logout', '/admin/logout', 'Sign out'),
        ]
        nav_html = ''.join(f"<a class='admin-nav-link {'active' if key == active else ''}' href='{href}'>{label}</a>" for key, href, label in nav)
        return html_response(self, 200, f"""<!doctype html><html><head><title>{esc(title)} - Mad Mallard Platform</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head>
<body class='admin-app'><aside class='admin-sidebar'><div class='admin-brand'><img src='/assets/mad-mallard-solutions-logo-icon.png' alt=''><div><strong>Mad Mallard</strong><span>Business OS</span></div></div><nav>{nav_html}</nav></aside><main class='admin-main'>{content}</main></body></html>""")

    def render_dashboard(self):
        summary = platform_core.dashboard_summary()
        org_cards = ''.join(f"""
<a class='org-card' href='/admin/organizations/{esc(o['slug'])}' style='--accent:{esc(o['brand_color'])}'>
  <div class='org-card-top'><span class='org-dot'></span><span class='badge status-{esc(o['status'])}'>{esc(o['status'])}</span></div>
  <h3>{esc(o['name'])}</h3>
  <p>{esc(o['business_type'])}</p>
  <small>{esc(o['public_domain'] or 'No public domain configured yet')}</small>
</a>""" for o in summary['organizations'])
        audit_rows = ''.join(f"<li><strong>{esc(a['action'])}</strong><span>{esc(a['detail'])}</span></li>" for a in summary['audit']) or '<li>No activity yet.</li>'
        content = f"""
<header class='admin-header'><div><p class='eyebrow'>Core Platform</p><h1>Dashboard</h1><p>One low-cost control plane for separate Mad Mallard business entities.</p></div><a class='btn primary' href='/admin/organizations'>Manage organizations</a></header>
<section class='metric-grid'>
  <div class='metric-card'><span>Organizations</span><strong>{len(summary['organizations'])}</strong><small>Separate brands, shared platform</small></div>
  <div class='metric-card'><span>Conversations</span><strong>{summary['conversation_count']}</strong><small>{esc(summary['status_counts'].get('new', 0))} new</small></div>
  <div class='metric-card'><span>Messages</span><strong>{summary['message_count']}</strong><small>Stored locally in SQLite</small></div>
  <div class='metric-card'><span>Cost posture</span><strong>Low</strong><small>EC2 + SQLite + SES</small></div>
</section>
<section class='admin-section'><div class='section-title'><h2>Business entities</h2><p>Each can have its own domain, branding, modules, and public identity.</p></div><div class='org-grid'>{org_cards}</div></section>
<section class='admin-section two-col'><div><h2>Next build targets</h2><ul class='todo-list'><li>CRM contacts and companies</li><li>Project records and task lists</li><li>Form builder per organization</li><li>Public pages per organization</li></ul></div><div><h2>Recent activity</h2><ul class='activity-list'>{audit_rows}</ul></div></section>
"""
        return self.admin_shell('Dashboard', content, 'dashboard')

    def render_organizations(self):
        orgs = platform_core.list_organizations()
        rows = ''.join(f"""
<tr><td><a href='/admin/organizations/{esc(o['slug'])}'>{esc(o['name'])}</a></td><td>{esc(o['business_type'])}</td><td>{esc(o['public_domain'] or '—')}</td><td><span class='badge status-{esc(o['status'])}'>{esc(o['status'])}</span></td></tr>""" for o in orgs)
        content = f"""
<header class='admin-header'><div><p class='eyebrow'>Core Platform</p><h1>Organizations</h1><p>These are separate business identities sharing the same low-cost platform.</p></div></header>
<section class='admin-card'><table class='admin-table'><thead><tr><th>Name</th><th>Type</th><th>Domain</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table></section>
"""
        return self.admin_shell('Organizations', content, 'organizations')

    def render_organization_detail(self, slug: str):
        org = platform_core.get_organization(slug)
        if not org:
            return self.admin_shell('Not found', '<h1>Organization not found</h1>', 'organizations')
        enabled = set(platform_core.parse_modules(org['enabled_modules']))
        module_checks = ''.join(f"<label class='check-pill'><input type='checkbox' name='modules' value='{esc(key)}' {'checked' if key in enabled else ''}> {esc(label)}</label>" for key, label in platform_core.MODULES.items())
        content = f"""
<header class='admin-header'><div><p class='eyebrow'>Organization Settings</p><h1>{esc(org['name'])}</h1><p>Manage identity, public domain, and enabled platform modules.</p></div><a class='btn secondary' href='/admin/organizations'>Back</a></header>
<form class='admin-card org-form' method='post' action='/admin/organizations/{esc(slug)}/save'>
  <div class='form-grid two'>
    <label>Name<input name='name' value='{esc(org['name'])}' required></label>
    <label>Legal name<input name='legal_name' value='{esc(org['legal_name'])}'></label>
    <label>Business type<input name='business_type' value='{esc(org['business_type'])}'></label>
    <label>Public domain<input name='public_domain' value='{esc(org['public_domain'])}' placeholder='example.com or subdomain.example.com'></label>
    <label>Brand color<input name='brand_color' type='color' value='{esc(org['brand_color'])}'></label>
    <label>Status<select name='status'><option value='active' {'selected' if org['status']=='active' else ''}>Active</option><option value='draft' {'selected' if org['status']=='draft' else ''}>Draft</option><option value='archived' {'selected' if org['status']=='archived' else ''}>Archived</option></select></label>
  </div>
  <h2>Enabled modules</h2><div class='module-grid'>{module_checks}</div>
  <label>Internal notes<textarea name='notes' rows='5'>{esc(org['notes'])}</textarea></label>
  <button class='btn primary' type='submit'>Save organization</button>
</form>
"""
        return self.admin_shell(org['name'], content, 'organizations')

    def handle_organization_save(self, slug: str, payload: dict):
        # read_body preserves repeated checkbox values as a list.
        selected = payload.get('modules', '')
        if isinstance(selected, list):
            selected_modules = selected
        else:
            # Browsers submit repeated checkboxes; read_body keeps one, so accept a comma list too.
            selected_modules = [p.strip() for p in str(selected).split(',') if p.strip()]
        ok = platform_core.update_organization(
            slug,
            actor=ADMIN_USERNAME,
            name=str(payload.get('name', '')),
            legal_name=str(payload.get('legal_name', '')),
            business_type=str(payload.get('business_type', '')),
            public_domain=str(payload.get('public_domain', '')),
            brand_color=str(payload.get('brand_color', '#36d1dc')),
            status=str(payload.get('status', 'draft')),
            enabled_modules=selected_modules,
            notes=str(payload.get('notes', '')),
        )
        return redirect(self, f'/admin/organizations/{slug}' if ok else '/admin/organizations')

    def render_login(self):
        if ADMIN_PASSWORD_HASH:
            body = f"""<!doctype html><html><head><title>Admin Login - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head>
<body class='conversation-page'><main class='conversation-shell auth-shell'><div class='admin-card'><h1>Admin login</h1><p>Sign in to manage leads, conversations, notes, and replies.</p><form method='post' action='/admin/login' class='contact-panel'><label>Username<input type='text' name='username' value='{esc(ADMIN_USERNAME)}' autocomplete='username' required autofocus></label><label>Password<input type='password' name='password' autocomplete='current-password' required></label><button class='btn primary' type='submit'>Open inbox</button></form></div></main></body></html>"""
        else:
            body = """<!doctype html><html><head><title>Admin Login - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head>
<body class='conversation-page'><main class='conversation-shell auth-shell'><div class='admin-card'><h1>Admin login</h1><p>Legacy token mode is active. Set <code>admin_password_hash</code> in Terraform to use username/password login.</p><form method='post' action='/admin/login' class='contact-panel'><label>Admin token<input type='password' name='token' autocomplete='current-password' required autofocus></label><button class='btn primary' type='submit'>Open inbox</button></form></div></main></body></html>"""
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
        counts = {status: 0 for status in messaging.STATUSES}
        for c in convos:
            counts[c['status']] = counts.get(c['status'], 0) + 1
        cards = []
        for c in convos:
            subject = esc(c['subject'] or c['kind'].replace('_', ' ').title())
            tags = ''.join(f"<span class='tag'>{esc(t.strip())}</span>" for t in (c['tags'] or '').split(',') if t.strip())
            cards.append(f"""
<a class='inbox-card priority-{esc(c['priority'])}' href='/admin/conversations/{esc(c['token'])}'>
  <div class='inbox-main'>
    <div class='inbox-title'><strong>{subject}</strong><span class='badge status-{esc(c['status'])}'>{esc(c['status']).replace('_',' ')}</span></div>
    <div class='inbox-contact'>{esc(c['name'] or 'Visitor')} · {esc(c['email'] or 'No email')} · {esc(c['company'] or 'No company')}</div>
    <div class='tag-row'>{tags or '<span class="tag muted">untagged</span>'}</div>
  </div>
  <div class='inbox-meta'><span>{esc(c['kind']).replace('_',' ')}</span><span>{esc(c['priority'])}</span></div>
</a>""")
        listing = ''.join(cards) or '<div class="empty-state">No conversations yet.</div>'
        stats = ''.join(f"<div class='stat'><strong>{counts.get(s,0)}</strong><span>{s.replace('_',' ')}</span></div>" for s in messaging.STATUSES)
        body = f"""<!doctype html><html><head><title>Inbox - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head><body class='conversation-page'><main class='conversation-shell wide admin-shell'><div class='admin-top'><div><p><a href='/'>← Site</a> · <a href='/admin/logout'>Sign out</a></p><h1>Mad Mallard Inbox</h1><p class='muted-text'>Manage project requests, chat threads, replies, internal notes, priority, and tags.</p></div></div><section class='stat-grid'>{stats}</section><section class='inbox-list'>{listing}</section></main></body></html>"""
        return html_response(self, 200, body)

    def render_admin_conversation(self, token: str):
        convo, messages = messaging.get_conversation(token)
        if not convo:
            return html_response(self, 404, '<h1>Conversation not found</h1>')
        rows = ''.join(f"<div class='msg {esc(m['sender_type'])}{' internal' if m['internal'] else ''}'><div class='msg-head'><strong>{esc(m['sender'])}</strong><span>{'Internal note' if m['internal'] else esc(m['sender_type'])}</span></div><p>{esc(m['body'])}</p></div>" for m in messages)
        status_opts = ''.join(f"<option value='{s}' {'selected' if convo['status']==s else ''}>{s.replace('_',' ')}</option>" for s in messaging.STATUSES)
        pri_opts = ''.join(f"<option value='{p}' {'selected' if convo['priority']==p else ''}>{p}</option>" for p in messaging.PRIORITIES)
        lead = json.loads(convo['lead_json'] or '{}')
        lead_rows = ''.join(f"<div><span>{esc(k).replace('_',' ').title()}</span><strong>{esc(v)}</strong></div>" for k,v in lead.items() if v)
        body = f"""<!doctype html><html><head><title>Conversation Admin - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head><body class='conversation-page'><main class='conversation-shell wide admin-shell'><p><a href='/admin/inbox'>← Inbox</a></p><div class='conversation-admin-grid'><section><div class='conversation-title'><span class='badge status-{esc(convo['status'])}'>{esc(convo['status']).replace('_',' ')}</span><h1>{esc(convo['subject'] or 'Conversation')}</h1><p class='muted-text'><strong>{esc(convo['name'])}</strong> · {esc(convo['email'])} · {esc(convo['company'])}</p></div><section class='message-list admin-messages'>{rows}</section><form id='replyForm' class='contact-panel'><h3>Reply</h3><textarea name='body' rows='5' placeholder='Reply to visitor or add internal note...' required></textarea><label class='check'><input type='checkbox' name='internal'> Internal note only</label><button class='btn primary' type='submit'>Send</button></form></section><aside class='admin-sidebar'><form id='metaForm' class='contact-panel'><h3>Manage</h3><label>Status<select name='status'>{status_opts}</select></label><label>Priority<select name='priority'>{pri_opts}</select></label><label>Tags<input name='tags' value='{esc(convo['tags'])}' placeholder='AWS, Terraform, urgent'></label><button class='btn secondary' type='submit'>Save changes</button></form><div class='contact-panel'><h3>Lead details</h3><div class='detail-grid'><div><span>Name</span><strong>{esc(convo['name'])}</strong></div><div><span>Email</span><strong>{esc(convo['email'])}</strong></div><div><span>Company</span><strong>{esc(convo['company'])}</strong></div>{lead_rows}</div><p><a class='btn secondary' href='/chat/{esc(convo['token'])}' target='_blank'>Open visitor link</a></p></div></aside></div></main><script>document.getElementById('replyForm').addEventListener('submit', async e=>{{e.preventDefault(); const fd=new FormData(e.target); const data=Object.fromEntries(fd.entries()); data.internal=e.target.internal.checked; const r=await fetch('/api/admin/conversations/{token}/messages',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}}); if(r.ok) location.reload();}});document.getElementById('metaForm').addEventListener('submit', async e=>{{e.preventDefault(); const data=Object.fromEntries(new FormData(e.target).entries()); const r=await fetch('/api/admin/conversations/{token}/update',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}}); if(r.ok) location.reload();}});</script></body></html>"""
        return html_response(self, 200, body)


if __name__ == '__main__':
    messaging.db()
    print(f'Mad Mallard Platform serving {PRIMARY_DOMAIN} on :8000', flush=True)
    ThreadingHTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
