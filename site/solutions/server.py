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
import time
import hmac
import hashlib
import base64
import messaging
import form_config

ROOT = Path('/app').resolve()
INDEX = ROOT / 'index.html'
def load_admin_config() -> dict:
    # Terraform writes this file during SSM app deploy from the values in terraform.tfvars.
    # Environment variables still override it, but the three Terraform variables remain
    # the source of truth for username/password admin login.
    config_path = Path('/data/admin_config.json')
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding='utf-8'))
    except Exception:
        return {}


ADMIN_CONFIG = load_admin_config()
ADMIN_TOKEN = (os.environ.get('MADMALLARD_ADMIN_TOKEN') or ADMIN_CONFIG.get('admin_token') or '').strip()
ADMIN_USERNAME = (os.environ.get('MADMALLARD_ADMIN_USERNAME') or ADMIN_CONFIG.get('admin_username') or 'admin').strip() or 'admin'
ADMIN_PASSWORD_HASH = (os.environ.get('MADMALLARD_ADMIN_PASSWORD_HASH') or ADMIN_CONFIG.get('admin_password_hash') or '').strip()
ADMIN_SESSION_SECRET = (os.environ.get('MADMALLARD_ADMIN_SESSION_SECRET') or ADMIN_CONFIG.get('admin_session_secret') or '').strip()
PRIMARY_DOMAIN = os.environ.get('MADMALLARD_PRIMARY_DOMAIN', 'pillar.madmallards.com')

FORM_CONFIG = {
    'services': form_config.select_options('service'),
    'timelines': form_config.select_options('timeline'),
    'budgets': form_config.select_options('budget'),
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


def admin_auth_configured() -> bool:
    return bool(ADMIN_USERNAME and ADMIN_PASSWORD_HASH and ADMIN_SESSION_SECRET)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def _b64url_decode(data: str) -> bytes:
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def verify_password(password: str, encoded_hash: str) -> bool:
    """Verify admin password.

    Preferred format:
      pbkdf2_sha256$<iterations>$<salt>$<hex_digest>

    A legacy sha256$<salt>$<hex_digest> format is also accepted so older
    locally generated hashes can continue to work.
    """
    if not password or not encoded_hash:
        return False
    try:
        if encoded_hash.startswith('pbkdf2_sha256$'):
            _, iterations, salt, expected = encoded_hash.split('$', 3)
            actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), int(iterations)).hex()
            return hmac.compare_digest(actual, expected)
        if encoded_hash.startswith('sha256$'):
            _, salt, expected = encoded_hash.split('$', 2)
            actual = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
            return hmac.compare_digest(actual, expected)
    except Exception:
        return False
    return False


def make_admin_session(username: str) -> str:
    secret = ADMIN_SESSION_SECRET or ADMIN_TOKEN
    payload = {
        'u': username,
        'exp': int(time.time()) + 60 * 60 * 24 * 30,
        'n': secrets.token_hex(8),
    }
    encoded = _b64url_encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
    sig = hmac.new(secret.encode('utf-8'), encoded.encode('utf-8'), hashlib.sha256).hexdigest()
    return f'{encoded}.{sig}'


def verify_admin_session(cookie_value: str) -> bool:
    secret = ADMIN_SESSION_SECRET or ADMIN_TOKEN
    if not secret or not cookie_value or '.' not in cookie_value:
        return False
    encoded, sig = cookie_value.rsplit('.', 1)
    expected = hmac.new(secret.encode('utf-8'), encoded.encode('utf-8'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        payload = json.loads(_b64url_decode(encoded).decode('utf-8'))
    except Exception:
        return False
    if payload.get('u') != ADMIN_USERNAME:
        return False
    if int(payload.get('exp', 0)) < int(time.time()):
        return False
    return True


def admin_is_authenticated(handler: BaseHTTPRequestHandler, query: dict | None = None) -> bool:
    if not admin_auth_configured():
        return False
    cookie_session = get_cookie(handler, 'mms_admin_session')
    if verify_admin_session(cookie_session):
        return True
    # Keep admin_token available for non-interactive/emergency access only.
    supplied = query.get('token', [''])[0] if query else ''
    return bool(ADMIN_TOKEN and supplied and secrets.compare_digest(supplied, ADMIN_TOKEN))


def require_admin(handler: BaseHTTPRequestHandler, query: dict | None = None) -> bool:
    if not admin_auth_configured():
        html_response(handler, 403, '<h1>Admin disabled</h1><p>Set admin_username, admin_password_hash, and admin_session_secret in Terraform to enable the inbox.</p>')
        return False
    if not admin_is_authenticated(handler, query):
        redirect(handler, '/admin/login')
        return False
    return True


def esc(value) -> str:
    return html.escape(str(value or ''))


def fmt_ts(ts: int | str | None) -> str:
    try:
        return time.strftime('%b %-d, %Y %-I:%M %p', time.localtime(int(ts)))
    except Exception:
        return ''


def status_label(status: str) -> str:
    return status.replace('_', ' ').title()


def rating_label(rating: str) -> str:
    return {'excellent':'😊 Excellent','good':'🙂 Good','ok':'😐 OK','needs_improvement':'🙁 Needs improvement'}.get(rating, rating)


class Handler(BaseHTTPRequestHandler):
    server_version = 'MadMallardPlatform/0.4'

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
            cfg = FORM_CONFIG | form_config.public_form_config()
            return json_response(self, 200, cfg)
        if path == '/request':
            return self.render_request_form()
        if path.startswith('/my-requests/'):
            return self.render_my_requests(path.rstrip('/').split('/')[-1])
        if path.startswith('/chat/'):
            return self.render_chat(path.rstrip('/').split('/')[-1])
        if path.startswith('/feedback/'):
            parts = path.strip('/').split('/')
            if len(parts) >= 3:
                return self.render_feedback(parts[1], parts[2])
        if path == '/admin/login':
            return self.render_login()
        if path == '/admin/logout':
            return html_response(self, 200, '<h1>Signed out</h1><p><a href="/admin/login">Sign in again</a></p>', {'Set-Cookie': 'mms_admin_session=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax'})
        if path == '/admin/inbox':
            if not require_admin(self, query):
                return
            return self.render_inbox(query)
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
            password = str(payload.get('password', ''))
            if admin_auth_configured() and secrets.compare_digest(username, ADMIN_USERNAME) and verify_password(password, ADMIN_PASSWORD_HASH):
                session = make_admin_session(username)
                return redirect(self, '/admin/inbox', {'Set-Cookie': f'mms_admin_session={session}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000'})
            return html_response(self, 403, '<h1>Invalid username or password</h1><p><a href="/admin/login">Try again</a></p>')

        if parsed.path == '/api/contact':
            return self.handle_project_request(payload)
        if parsed.path == '/api/chat/start':
            return self.handle_chat_start(payload)
        if parsed.path.startswith('/api/chat/') and parsed.path.endswith('/messages'):
            token = parsed.path.split('/')[3]
            return self.handle_visitor_message(token, payload)
        if parsed.path.startswith('/api/chat/') and parsed.path.endswith('/feedback'):
            token = parsed.path.split('/')[3]
            return self.handle_visitor_feedback(token, payload)
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
        convo = messaging.create_conversation(kind='project_request', name=name, email=email, company=company, subject=subject, body=body, tags=[service] if service else [], lead={'service': service, 'timeline': timeline, 'budget': budget, 'message': message})
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

    def handle_visitor_feedback(self, token: str, payload: dict):
        rating = str(payload.get('rating', '')).strip()
        comment = str(payload.get('comment', '')).strip()
        ok = messaging.record_feedback_by_conversation(token, rating, comment)
        return json_response(self, 200 if ok else 400, {'ok': ok})

    def render_feedback(self, feedback_token: str, rating: str):
        if rating not in messaging.RATINGS:
            return html_response(self, 400, '<h1>Invalid feedback option</h1>')
        ok = messaging.record_feedback_by_message_token(feedback_token, rating)
        title = 'Thanks for the feedback' if ok else 'Feedback link not found'
        body = f"""<!doctype html><html><head><title>{title}</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head><body class='conversation-page'><main class='conversation-shell'><h1>{title}</h1><p>{'We recorded your rating: ' + esc(rating_label(rating)) if ok else 'This feedback link may have expired or already been changed.'}</p><p><a class='btn secondary' href='/'>Back to Mad Mallard Solutions</a></p></main></body></html>"""
        return html_response(self, 200 if ok else 404, body)

    def render_login(self):
        if not admin_auth_configured():
            return html_response(self, 403, """<!doctype html><html><head><title>Admin Disabled - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head><body class='conversation-page'><main class='conversation-shell'><h1>Admin disabled</h1><p>Set <code>admin_username</code>, <code>admin_password_hash</code>, and <code>admin_session_secret</code> in Terraform to enable username/password login.</p></main></body></html>""")
        body = """<!doctype html><html><head><title>Admin Login - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head>
<body class='conversation-page'><main class='conversation-shell'><h1>Admin login</h1><p>Sign in with your admin username and password. This browser will remember you for 30 days.</p><form method='post' action='/admin/login' class='contact-panel'><label>Username<input type='text' name='username' autocomplete='username' required autofocus></label><label>Password<input type='password' name='password' autocomplete='current-password' required></label><button class='btn primary' type='submit'>Open inbox</button></form></main></body></html>"""
        return html_response(self, 200, body)

    def render_request_form(self):
        def field_html(field):
            name = esc(field['name'])
            label = esc(field['label'])
            required = ' required' if field.get('required') else ''
            placeholder = esc(field.get('placeholder', ''))
            if field['type'] == 'textarea':
                return f"<label>{label}<textarea name='{name}' rows='6' placeholder='{placeholder}'{required}></textarea></label>"
            if field['type'] == 'select':
                opts = ''.join(f"<option value='{esc(o)}'>{esc(o)}</option>" for o in field.get('options', []))
                return f"<label>{label}<select name='{name}'{required}>{opts}</select></label>"
            return f"<label>{label}<input name='{name}' type='{esc(field['type'])}' placeholder='{placeholder}'{required}></label>"
        fields = ''.join(field_html(field) for field in form_config.REQUEST_FORM_FIELDS)
        body = f"""<!doctype html><html><head><title>Start a Request - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head>
<body class='conversation-page'><main class='conversation-shell'><a href='/'>← Back</a><h1>Start a request</h1><p>Tell us what you need. This creates a private request thread where you can continue the conversation and track status.</p><form id='requestForm' class='contact-panel'>{fields}<input type='text' name='website' tabindex='-1' autocomplete='off' class='hp-field'><button class='btn primary' type='submit'>Create request</button><p id='requestStatus' class='form-status'></p></form></main><script>document.getElementById('requestForm').addEventListener('submit',async e=>{{e.preventDefault();const data=Object.fromEntries(new FormData(e.target).entries());const status=document.getElementById('requestStatus');status.textContent='Creating request...';const r=await fetch('/api/contact',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}});const j=await r.json().catch(()=>({{ok:false,error:'Unexpected response'}}));if(j.ok){{status.innerHTML='Request created. <a href="'+j.conversation_url+'">Open conversation</a> · <a href="'+j.my_requests_url+'">My requests</a>'; e.target.reset();}} else {{status.textContent=j.error||'Could not create request.';}}}});</script></body></html>"""
        return html_response(self, 200, body)

    def render_my_requests(self, token: str):
        requests = messaging.get_customer_requests(token)
        if not requests:
            return html_response(self, 404, "<h1>Requests not found</h1><p>This private request link was not found.</p>")
        cards = []
        for req in requests:
            cards.append(f"<article class='request-card'><div><span class='badge status-{esc(req['status'])}'>{esc(status_label(req['status']))}</span><h3>{esc(req['subject'] or 'Request')}</h3><p>{esc(req['company'])}</p><p>Updated {esc(fmt_ts(req['updated_at']))}</p></div><a class='btn secondary' href='/chat/{esc(req['token'])}'>Open</a></article>")
        body = f"""<!doctype html><html><head><title>My Requests - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head>
<body class='conversation-page'><main class='conversation-shell wide'><a href='/'>← Back</a><div class='thread-header'><h1>My Requests</h1><a class='btn primary' href='/request'>New request</a></div><p>This private page lists the requests associated with your email address.</p><section class='request-list'>{''.join(cards)}</section></main></body></html>"""
        return html_response(self, 200, body)

    def render_chat(self, token: str):
        convo, messages = messaging.get_conversation(token)
        if not convo:
            return html_response(self, 404, '<h1>Conversation not found</h1>')
        visible = [m for m in messages if not m['internal']]
        rows = ''.join(f"<div class='msg {esc(m['sender_type'])}'><div class='msg-meta'><strong>{esc(m['sender'])}</strong><span>{esc(fmt_ts(m['created_at']))}</span></div><p>{esc(m['body'])}</p></div>" for m in visible)
        feedback_target = messaging.latest_feedback_target(token)
        feedback_card = ''
        if feedback_target:
            feedback = ''.join(f"<button type='button' data-rating='{r}'>{label}</button>" for r, label in [('excellent','😊 Excellent'),('good','🙂 Good'),('ok','😐 OK'),('needs_improvement','🙁 Needs improvement')])
            feedback_card = f"""<section class='feedback-card'><strong>Optional feedback</strong><p>How helpful was the latest response from Mad Mallard Solutions?</p><div class='feedback-buttons'>{feedback}</div><textarea id='feedbackComment' rows='3' placeholder='Optional: tell us how we could improve.'></textarea><p id='feedbackStatus'></p></section>"""
        feedback_script = """document.querySelectorAll('.feedback-buttons button').forEach(btn=>btn.addEventListener('click', async()=>{const comment=document.getElementById('feedbackComment').value; const r=await fetch('/api/chat/%s/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rating:btn.dataset.rating, comment})}); document.getElementById('feedbackStatus').textContent=r.ok?'Thanks — your feedback was recorded.':'Sorry, feedback could not be saved.';}));""" % token if feedback_target else ''
        body = f"""<!doctype html><html><head><title>Conversation - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head>
<body class='conversation-page'><main class='conversation-shell'><a href='/'>← Back</a><div class='thread-header'><h1>Conversation</h1><span class='badge status-{esc(convo['status'])}'>{esc(status_label(convo['status']))}</span></div><p>This private link lets you continue the conversation with Mad Mallard Solutions.</p><section class='message-list'>{rows}</section>{feedback_card}<form id='replyForm' class='contact-panel'><textarea name='body' rows='5' placeholder='Add a message...' required></textarea><button class='btn primary' type='submit'>Send message</button></form></main><script>document.getElementById('replyForm').addEventListener('submit', async e=>{{e.preventDefault(); const body=e.target.body.value; const r=await fetch('/api/chat/{token}/messages',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{body}})}}); if(r.ok) location.reload();}});{feedback_script}</script></body></html>"""
        return html_response(self, 200, body)

    def render_inbox(self, query: dict):
        status = query.get('status', [''])[0]
        q = query.get('q', [''])[0]
        tag = query.get('tag', [''])[0]
        convos = messaging.list_conversations(status=status, q=q, tag=tag)
        stats = messaging.inbox_stats()
        count_cards = ''.join(f"<a class='dash-card' href='/admin/inbox?status={s}'><span>{status_label(s)}</span><strong>{stats['counts'].get(s,0)}</strong></a>" for s in ['new','waiting_on_me','waiting_on_client','in_progress','closed'])
        feedback_total = sum(stats['feedback'].values()) or 0
        happy = stats['feedback'].get('excellent',0) + stats['feedback'].get('good',0)
        score = round((happy / feedback_total) * 100) if feedback_total else 0
        rows = []
        for c in convos:
            feedback = f"<span class='feedback-chip'>{esc(rating_label(c['last_feedback_rating']))}</span>" if c['last_feedback_rating'] else ''
            rows.append(f"<a class='inbox-item priority-{esc(c['priority'])}' href='/admin/conversations/{esc(c['token'])}'><div><strong>{esc(c['subject'] or c['name'] or 'Visitor')}</strong><small>{esc(c['name'])} · {esc(c['email'])} · {esc(c['company'])}</small></div><div class='inbox-meta'><span class='badge status-{esc(c['status'])}'>{esc(status_label(c['status']))}</span><span>{esc(c['priority'])}</span>{feedback}<small>{esc(fmt_ts(c['updated_at']))}</small></div></a>")
        listing = ''.join(rows) or '<div class="empty-state">No conversations match this filter.</div>'
        body = f"""<!doctype html><html><head><title>Inbox - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head><body class='conversation-page'><main class='conversation-shell wide'><p><a href='/'>← Site</a> · <a href='/admin/logout'>Sign out</a></p><div class='admin-hero'><div><span class='eyebrow'>Conversations</span><h1>Mad Mallard Inbox</h1><p>Manage project requests, visitor chats, replies, internal notes, and optional response feedback.</p></div><div class='score-card'><span>Satisfaction</span><strong>{score}%</strong><small>{feedback_total} feedback responses</small></div></div><section class='dashboard-grid'>{count_cards}</section><form class='inbox-search' method='get'><input name='q' value='{esc(q)}' placeholder='Search name, email, company, subject, tags'><input name='tag' value='{esc(tag)}' placeholder='Filter tag'><button class='btn secondary' type='submit'>Search</button><a class='btn secondary' href='/admin/inbox'>Clear</a></form><section class='inbox-list'>{listing}</section></main></body></html>"""
        return html_response(self, 200, body)

    def render_admin_conversation(self, token: str):
        convo, messages = messaging.get_conversation(token)
        if not convo:
            return html_response(self, 404, '<h1>Conversation not found</h1>')
        rows = ''.join(f"<div class='msg {esc(m['sender_type'])}{' internal' if m['internal'] else ''}'><div class='msg-meta'><strong>{esc(m['sender'])}{' · internal note' if m['internal'] else ''}</strong><span>{esc(fmt_ts(m['created_at']))}</span></div><p>{esc(m['body'])}</p></div>" for m in messages)
        status_opts = ''.join(f"<option value='{s}' {'selected' if convo['status']==s else ''}>{status_label(s)}</option>" for s in messaging.STATUSES)
        pri_opts = ''.join(f"<option value='{p}' {'selected' if convo['priority']==p else ''}>{p.title()}</option>" for p in messaging.PRIORITIES)
        feedback_banner = f"<div class='feedback-card'><strong>Latest feedback:</strong> {esc(rating_label(convo['last_feedback_rating']))}</div>" if convo['last_feedback_rating'] else ''
        body = f"""<!doctype html><html><head><title>Conversation Admin - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head><body class='conversation-page'><main class='conversation-shell'><p><a href='/admin/inbox'>← Inbox</a></p><div class='thread-header'><h1>{esc(convo['subject'] or 'Conversation')}</h1><span class='badge status-{esc(convo['status'])}'>{esc(status_label(convo['status']))}</span></div><p><strong>{esc(convo['name'])}</strong> · {esc(convo['email'])} · {esc(convo['company'])}</p>{feedback_banner}<form id='metaForm' class='contact-panel compact'><label>Status<select name='status'>{status_opts}</select></label><label>Priority<select name='priority'>{pri_opts}</select></label><label>Tags<input name='tags' value='{esc(convo['tags'])}' placeholder='AWS, Terraform, Website'></label><button class='btn secondary' type='submit'>Save</button></form><section class='message-list'>{rows}</section><form id='replyForm' class='contact-panel'><textarea name='body' rows='5' placeholder='Reply to visitor or add internal note...' required></textarea><label class='check'><input type='checkbox' name='internal'> Internal note only</label><div class='saved-replies'><button type='button' data-template='Thanks for reaching out. I can help with this. Can you share a little more about your timeline and what you already have in place?'>/thanks</button><button type='button' data-template='For AWS/Terraform work, the next best step is usually a short discovery call so I can understand your current environment and constraints.'>/aws</button><button type='button' data-template='I received this and will take a closer look. I will follow up with next steps shortly.'>/received</button></div><button class='btn primary' type='submit'>Send</button></form></main><script>document.querySelectorAll('.saved-replies button').forEach(b=>b.addEventListener('click',()=>{{document.querySelector('#replyForm textarea').value=b.dataset.template;}}));document.getElementById('replyForm').addEventListener('submit', async e=>{{e.preventDefault(); const fd=new FormData(e.target); const data=Object.fromEntries(fd.entries()); data.internal=e.target.internal.checked; const r=await fetch('/api/admin/conversations/{token}/messages',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}}); if(r.ok) location.reload();}});document.getElementById('metaForm').addEventListener('submit', async e=>{{e.preventDefault(); const data=Object.fromEntries(new FormData(e.target).entries()); const r=await fetch('/api/admin/conversations/{token}/update',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}}); if(r.ok) location.reload();}});</script></body></html>"""
        return html_response(self, 200, body)


if __name__ == '__main__':
    messaging.db()
    print(f'Mad Mallard Platform serving {PRIMARY_DOMAIN} on :8000', flush=True)
    ThreadingHTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
