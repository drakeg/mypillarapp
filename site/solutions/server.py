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
import tenant_auth
import request_context
import tenant_conversations

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


SITES_PATH = Path('/data/sites.json')
DEFAULT_SITES = [
    {
        'id': 'solutions',
        'name': 'Mad Mallard Solutions',
        'domain': PRIMARY_DOMAIN,
        'status': 'Active',
        'purpose': 'IT, AWS, automation, and platform services',
        'brand': 'Dark blue / cyan technical services brand',
    },
    {
        'id': 'adventures',
        'name': 'Mad Mallards Adventures',
        'domain': 'madmallards.com',
        'status': 'Planned',
        'purpose': 'RV travel, creator content, affiliate hub',
        'brand': 'Adventure, travel, creator brand',
    },
    {
        'id': 'personal-training',
        'name': 'Mad Mallard Personal Training',
        'domain': 'madmallardpersonaltraining.com',
        'status': 'Planned',
        'purpose': 'Fitness services, client resources, training programs',
        'brand': 'Fitness and coaching brand',
    },
]


def _site_slug(value: str) -> str:
    cleaned = ''.join(ch.lower() if ch.isalnum() else '-' for ch in str(value or '').strip())
    while '--' in cleaned:
        cleaned = cleaned.replace('--', '-')
    return cleaned.strip('-') or secrets.token_urlsafe(6).lower()


def load_sites() -> list[dict]:
    if not SITES_PATH.exists():
        return [dict(site) for site in DEFAULT_SITES]
    try:
        data = json.loads(SITES_PATH.read_text(encoding='utf-8'))
        if isinstance(data, list):
            return [site for site in data if isinstance(site, dict)]
    except Exception:
        pass
    return [dict(site) for site in DEFAULT_SITES]


def save_sites(sites: list[dict]) -> None:
    SITES_PATH.parent.mkdir(parents=True, exist_ok=True)
    SITES_PATH.write_text(json.dumps(sites, indent=2, sort_keys=True), encoding='utf-8')


def get_site(site_id: str) -> dict | None:
    for site in load_sites():
        if site.get('id') == site_id:
            return site
    return None


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


def admin_head(title: str) -> str:
    return f"""<!doctype html><html><head><title>{esc(title)} - Mad Mallard Solutions Admin</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'><link rel='stylesheet' href='/assets/admin.css'></head>"""


def admin_nav(active: str = '') -> str:
    items = [
        ('/admin', 'dashboard', 'Dashboard'),
        ('/admin/inbox', 'inbox', 'Inbox'),
        ('/admin/requests', 'requests', 'Service Requests'),
        ('/admin/leads', 'leads', 'Leads'),
        ('/admin/crm', 'crm', 'CRM'),
        ('/admin/sites', 'sites', 'Sites'),
        ('/admin/settings', 'settings', 'Settings'),
    ]
    links = ''.join(f"<a class='{('active' if key == active else '')}' href='{href}'><span>{label}</span></a>" for href, key, label in items)
    return f"""<aside class='admin-sidebar'><a class='admin-brand' href='/admin'><img src='/assets/mad-mallard-solutions-logo-icon.png' alt=''><strong>Mad Mallard</strong><small>Solutions Admin</small></a><nav>{links}</nav><div class='admin-sidebar-footer'><a href='/'>View site</a><a href='/admin/logout'>Sign out</a></div></aside>"""


def admin_layout(title: str, active: str, content: str) -> str:
    return f"""{admin_head(title)}<body class='admin-page'>{admin_nav(active)}<main class='admin-main'>{content}</main></body></html>"""


def admin_page_header(eyebrow: str, title: str, subtitle: str = '', actions: str = '') -> str:
    return f"""<header class='admin-page-header'><div><span class='admin-eyebrow'>{esc(eyebrow)}</span><h1>{esc(title)}</h1>{f'<p>{esc(subtitle)}</p>' if subtitle else ''}</div><div class='admin-header-actions'>{actions}</div></header>"""


def public_account_nav(handler: BaseHTTPRequestHandler) -> str:
    context = request_context.build_request_context(
        handler.headers,
        get_cookie(handler, tenant_auth.SESSION_COOKIE),
    )
    user = context.user if context else None
    if user:
        name = esc(user['first_name'] or user['email'])
        return (
            f"<a href='/dashboard'>Dashboard</a>"
            f"<a href='/dashboard'>{name}</a>"
            "<a href='/logout'>Logout</a>"
        )
    return "<a href='/login'>Sign In</a><a href='/register'>Register</a>"


class Handler(BaseHTTPRequestHandler):
    server_version = 'MadMallardPlatform/0.4'

    def log_message(self, fmt, *args):
        print('%s - - [%s] %s' % (self.client_address[0], self.log_date_time_string(), fmt % args), flush=True)

    def request_context(self):
        return request_context.build_request_context(
            self.headers,
            get_cookie(self, tenant_auth.SESSION_COOKIE),
        )

    def require_public_tenant(self, path: str):
        if path.startswith('/admin') or path.startswith('/assets/'):
            return True, None
        context = self.request_context()
        if context is None:
            html_response(
                self,
                421,
                '<h1>Unknown site</h1><p>This host is not configured for an active tenant.</p>',
            )
            return False, None
        return True, context

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
        allowed, context = self.require_public_tenant(path)
        if not allowed:
            return

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
        if path == '/register':
            return html_response(self, 200, tenant_auth.render_register())
        if path == '/login':
            user = context.user if context else None
            if user:
                return redirect(self, '/dashboard')
            return html_response(self, 200, tenant_auth.render_login())
        if path == '/logout':
            tenant_auth.logout_session(get_cookie(self, tenant_auth.SESSION_COOKIE))
            return redirect(self, '/login', {'Set-Cookie': tenant_auth.clear_session_cookie()})
        if path == '/forgot-password':
            return html_response(self, 200, tenant_auth.render_forgot())
        if path.startswith('/verify-email/'):
            token = path.rstrip('/').split('/')[-1]
            ok, message, session = tenant_auth.verify_email(token)
            if ok:
                return redirect(self, '/dashboard', {'Set-Cookie': tenant_auth.session_cookie(session)})
            return html_response(self, 400, tenant_auth.page('Email Verification', f'<h1>Verification failed</h1><p>{esc(message)}</p><p><a href="/login">Sign in</a></p>'))
        if path.startswith('/reset-password/'):
            token = path.rstrip('/').split('/')[-1]
            return html_response(self, 200, tenant_auth.render_reset(token))
        if path == '/dashboard':
            user = context.user if context else None
            if not user:
                return redirect(self, '/login')
            return html_response(self, 200, tenant_auth.render_dashboard(user))
        if path == '/profile':
            user = context.user if context else None
            if not user:
                return redirect(self, '/login')
            return html_response(self, 200, tenant_auth.render_profile(user))
        if path == '/conversations':
            user = context.user if context else None
            if not user:
                return redirect(self, '/login')
            return html_response(self, 200, tenant_auth.render_customer_history(user, 'chat'))
        if path == '/requests':
            user = context.user if context else None
            if not user:
                return redirect(self, '/login')
            return html_response(self, 200, tenant_auth.render_customer_history(user, 'project_request'))
        if path.startswith('/account/conversations/'):
            user = tenant_auth.current_user(get_cookie(self, tenant_auth.SESSION_COOKIE))
            if not user:
                return redirect(self, '/login')
            token = path.rstrip('/').split('/')[-1]
            body = tenant_auth.render_customer_conversation(user, token)
            if body is None:
                return html_response(
                    self,
                    404,
                    tenant_auth.page(
                        'Not Found',
                        '<h1>Conversation not found</h1>'
                        '<p>The requested conversation is unavailable.</p>'
                        '<p><a href="/dashboard">Return to dashboard</a></p>',
                    ),
                )
            return html_response(self, 200, body)
        if path == '/admin/login':
            return self.render_login()
        if path == '/admin/logout':
            return html_response(self, 200, '<h1>Signed out</h1><p><a href="/admin/login">Sign in again</a></p>', {'Set-Cookie': 'mms_admin_session=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax'})
        if path == '/admin' or path == '/admin/':
            if not require_admin(self, query):
                return
            return self.render_admin_dashboard()
        if path == '/admin/inbox':
            if not require_admin(self, query):
                return
            return self.render_inbox(query)
        if path == '/admin/requests':
            if not require_admin(self, query):
                return
            return self.render_admin_requests(query)
        if path == '/admin/leads':
            if not require_admin(self, query):
                return
            return self.render_admin_leads(query)
        if path == '/admin/crm':
            if not require_admin(self, query):
                return
            return self.render_admin_crm(query)
        if path == '/admin/sites/new':
            if not require_admin(self, query):
                return
            return self.render_admin_site_form()
        if path.startswith('/admin/sites/') and path.endswith('/edit'):
            if not require_admin(self, query):
                return
            return self.render_admin_site_form(path.strip('/').split('/')[2])
        if path == '/admin/sites':
            if not require_admin(self, query):
                return
            return self.render_admin_sites()
        if path == '/admin/settings':
            if not require_admin(self, query):
                return
            return self.render_admin_settings()
        if path.startswith('/admin/conversations/'):
            if not require_admin(self, query):
                return
            return self.render_admin_conversation(path.rstrip('/').split('/')[-1])

        file_path = self._resolve_path()
        if file_path and file_path.exists():
            if file_path == INDEX:
                body = file_path.read_text(encoding='utf-8').replace('<!--ACCOUNT_NAV-->', public_account_nav(self))
                return html_response(self, 200, body)
            return self._send_file(file_path)
        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        payload = read_body(self)
        allowed, context = self.require_public_tenant(parsed.path)
        if not allowed:
            return

        if parsed.path == '/register':
            password = str(payload.get('password', ''))
            confirm = str(payload.get('password_confirm', ''))
            if password != confirm:
                return html_response(self, 400, tenant_auth.render_register('Passwords do not match.', True))
            ok, message = tenant_auth.register_user(
                organization_slug=context.tenant.slug,
                first_name=str(payload.get('first_name', '')).strip(),
                last_name=str(payload.get('last_name', '')).strip(),
                email=str(payload.get('email', '')).strip(),
                password=password,
            )
            status = 200 if ok else 400
            body = tenant_auth.page('Registration', f'<h1>{"Check your email" if ok else "Registration failed"}</h1><p>{esc(message)}</p><p><a href="/login">Sign in</a></p>') if ok else tenant_auth.render_register(message, True)
            return html_response(self, status, body)
        if parsed.path == '/login':
            ok, message, session = tenant_auth.login_user(
                str(payload.get('email', '')),
                str(payload.get('password', '')),
            )
            if ok:
                user = tenant_auth.current_user(session)
                if request_context.user_belongs_to_tenant(user, context.tenant):
                    return redirect(
                        self,
                        '/dashboard',
                        {'Set-Cookie': tenant_auth.session_cookie(session)},
                    )
                tenant_auth.logout_session(session)
                message = 'Invalid email or password.'
            return html_response(self, 403, tenant_auth.render_login(message, True))
        if parsed.path == '/forgot-password':
            tenant_auth.request_password_reset(str(payload.get('email', '')))
            return html_response(self, 200, tenant_auth.render_forgot('If an active account exists for that email, a reset link has been sent.'))
        if parsed.path.startswith('/reset-password/'):
            token = parsed.path.rstrip('/').split('/')[-1]
            password = str(payload.get('password', ''))
            confirm = str(payload.get('password_confirm', ''))
            if password != confirm:
                return html_response(self, 400, tenant_auth.render_reset(token, 'Passwords do not match.', True))
            ok, message = tenant_auth.reset_password(token, password)
            if ok:
                return html_response(self, 200, tenant_auth.page('Password Changed', f'<h1>Password changed</h1><p>{esc(message)}</p><p><a href="/login">Sign in</a></p>'))
            return html_response(self, 400, tenant_auth.render_reset(token, message, True))
        if parsed.path == '/profile':
            session_token = get_cookie(self, tenant_auth.SESSION_COOKIE)
            user = context.user if context else None
            if not user:
                return redirect(self, '/login')
            action = str(payload.get('action', 'profile'))
            if action == 'password':
                password = str(payload.get('password', ''))
                confirm = str(payload.get('password_confirm', ''))
                if password != confirm:
                    return html_response(self, 400, tenant_auth.render_profile(user, 'New passwords do not match.', True))
                ok, message = tenant_auth.change_password(int(user['id']), str(payload.get('current_password', '')), password)
                if not ok:
                    return html_response(self, 400, tenant_auth.render_profile(user, message, True))
                return redirect(self, '/login', {'Set-Cookie': tenant_auth.clear_session_cookie()})
            ok, message = tenant_auth.update_profile(
                int(user['id']),
                str(payload.get('first_name', '')),
                str(payload.get('last_name', '')),
                str(payload.get('email', '')),
            )
            refreshed = tenant_auth.current_user(session_token) or user
            return html_response(self, 200 if ok else 400, tenant_auth.render_profile(refreshed, message, not ok))

        if parsed.path == '/admin/login':
            username = str(payload.get('username', '')).strip()
            password = str(payload.get('password', ''))
            if admin_auth_configured() and secrets.compare_digest(username, ADMIN_USERNAME) and verify_password(password, ADMIN_PASSWORD_HASH):
                session = make_admin_session(username)
                return redirect(self, '/admin', {'Set-Cookie': f'mms_admin_session={session}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000'})
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
        if parsed.path == '/api/admin/sites/save':
            query = parse_qs(parsed.query)
            if not require_admin(self, query):
                return
            return self.handle_admin_site_save(payload)
        if parsed.path == '/api/admin/sites/delete':
            query = parse_qs(parsed.query)
            if not require_admin(self, query):
                return
            return self.handle_admin_site_delete(payload)

        self.send_error(404)

    def handle_admin_site_save(self, payload: dict):
        site_id = str(payload.get('id', '')).strip()
        name = str(payload.get('name', '')).strip()
        domain = str(payload.get('domain', '')).strip()
        status = str(payload.get('status', 'Planned')).strip() or 'Planned'
        purpose = str(payload.get('purpose', '')).strip()
        brand = str(payload.get('brand', '')).strip()
        if not name or not domain:
            return json_response(self, 400, {'ok': False, 'error': 'Name and domain are required.'})
        sites = load_sites()
        if not site_id:
            site_id = _site_slug(name)
            existing_ids = {s.get('id') for s in sites}
            base = site_id
            i = 2
            while site_id in existing_ids:
                site_id = f'{base}-{i}'
                i += 1
            sites.append({'id': site_id, 'name': name, 'domain': domain, 'status': status, 'purpose': purpose, 'brand': brand})
        else:
            updated = False
            for site in sites:
                if site.get('id') == site_id:
                    site.update({'name': name, 'domain': domain, 'status': status, 'purpose': purpose, 'brand': brand})
                    updated = True
                    break
            if not updated:
                sites.append({'id': site_id, 'name': name, 'domain': domain, 'status': status, 'purpose': purpose, 'brand': brand})
        save_sites(sites)
        return json_response(self, 200, {'ok': True, 'redirect': '/admin/sites'})

    def handle_admin_site_delete(self, payload: dict):
        site_id = str(payload.get('id', '')).strip()
        if not site_id:
            return json_response(self, 400, {'ok': False, 'error': 'Site id is required.'})
        sites = [site for site in load_sites() if site.get('id') != site_id]
        save_sites(sites)
        return json_response(self, 200, {'ok': True, 'redirect': '/admin/sites'})

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
        context = self.request_context()
        if not context:
            return json_response(self, 404, {'ok': False, 'error': 'Unknown tenant.'})
        convo = tenant_conversations.create_conversation(tenant_slug=context.tenant.slug, kind='project_request', name=name, email=email, company=company, subject=subject, body=body, tags=[service] if service else [], lead={'service': service, 'timeline': timeline, 'budget': budget, 'message': message})
        messaging.notify_new_conversation(convo, body)
        messaging.notify_visitor_link(convo)
        return json_response(self, 200, {'ok': True, 'message': 'Thanks. Your request was saved.', 'conversation_url': f'/chat/{convo["token"]}'})

    def handle_chat_start(self, payload: dict):
        name = str(payload.get('name', '')).strip() or 'Visitor'
        email = str(payload.get('email', '')).strip()
        body = str(payload.get('body', '')).strip()
        if not body:
            return json_response(self, 400, {'ok': False, 'error': 'Please enter a message.'})
        context = self.request_context()
        if not context:
            return json_response(self, 404, {'ok': False, 'error': 'Unknown tenant.'})
        convo = tenant_conversations.create_conversation(tenant_slug=context.tenant.slug, kind='chat', name=name, email=email, subject='Website chat', body=body, tags=['chat'])
        messaging.notify_new_conversation(convo, body)
        messaging.notify_visitor_link(convo)
        return json_response(self, 200, {'ok': True, 'url': f'/chat/{convo["token"]}', 'full_url': messaging.public_url(f'/chat/{convo["token"]}')})

    def handle_visitor_message(self, token: str, payload: dict):
        body = str(payload.get('body', '')).strip()
        sender = str(payload.get('sender', 'Visitor')).strip() or 'Visitor'
        if not body:
            return json_response(self, 400, {'ok': False, 'error': 'Message is required.'})
        context = self.request_context()
        if not context:
            return json_response(self, 404, {'ok': False, 'error': 'Unknown tenant.'})
        convo = tenant_conversations.add_message(context.tenant.slug, token, body=body, sender=sender, sender_type='visitor')
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
        feedback = ''.join(f"<button type='button' data-rating='{r}'>{label}</button>" for r, label in [('excellent','😊 Excellent'),('good','🙂 Good'),('ok','😐 OK'),('needs_improvement','🙁 Needs improvement')])
        body = f"""<!doctype html><html><head><title>Conversation - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head>
<body class='conversation-page'><main class='conversation-shell'><a href='/'>← Back</a><div class='thread-header'><h1>Conversation</h1><span class='badge status-{esc(convo['status'])}'>{esc(status_label(convo['status']))}</span></div><p>This private link lets you continue the conversation with Mad Mallard Solutions.</p><section class='message-list'>{rows}</section><section class='feedback-card'><strong>Optional feedback</strong><p>How helpful was the latest response?</p><div class='feedback-buttons'>{feedback}</div><textarea id='feedbackComment' rows='3' placeholder='Optional: tell us how we could improve.'></textarea><p id='feedbackStatus'></p></section><form id='replyForm' class='contact-panel'><textarea name='body' rows='5' placeholder='Add a message...' required></textarea><button class='btn primary' type='submit'>Send message</button></form></main><script>document.getElementById('replyForm').addEventListener('submit', async e=>{{e.preventDefault(); const body=e.target.body.value; const r=await fetch('/api/chat/{token}/messages',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{body}})}}); if(r.ok) location.reload();}});document.querySelectorAll('.feedback-buttons button').forEach(btn=>btn.addEventListener('click', async()=>{{const comment=document.getElementById('feedbackComment').value; const r=await fetch('/api/chat/{token}/feedback',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{rating:btn.dataset.rating, comment}})}}); document.getElementById('feedbackStatus').textContent=r.ok?'Thanks — your feedback was recorded.':'Sorry, feedback could not be saved.';}}));</script></body></html>"""
        return html_response(self, 200, body)

    def render_admin_dashboard(self):
        stats = messaging.inbox_stats()
        feedback_total = sum(stats['feedback'].values()) or 0
        happy = stats['feedback'].get('excellent', 0) + stats['feedback'].get('good', 0)
        score = round((happy / feedback_total) * 100) if feedback_total else 0
        recent = messaging.list_conversations(limit=6)
        cards = ''.join(
            f"<a class='admin-stat-card' href='/admin/inbox?status={s}'><span>{status_label(s)}</span><strong>{stats['counts'].get(s, 0)}</strong></a>"
            for s in ['new', 'waiting_on_me', 'waiting_on_client', 'in_progress', 'closed']
        )
        recent_rows = ''.join(
            f"<a class='admin-list-row' href='/admin/conversations/{esc(c['token'])}'><div><strong>{esc(c['subject'] or c['name'] or 'Conversation')}</strong><small>{esc(c['name'])} · {esc(c['email'])}</small></div><span class='badge status-{esc(c['status'])}'>{esc(status_label(c['status']))}</span></a>"
            for c in recent
        ) or "<div class='admin-empty'>No conversations yet.</div>"
        content = admin_page_header('Dashboard', 'Operations dashboard', 'Quick view of requests, conversations, leads, and site status.') + f"""
<section class='admin-stats'>{cards}<a class='admin-stat-card' href='/admin/inbox'><span>Satisfaction</span><strong>{score}%</strong></a></section>
<section class='admin-grid two'><article class='admin-panel'><div class='panel-title'><h2>Recent conversations</h2><a href='/admin/inbox'>View all</a></div><div class='admin-list'>{recent_rows}</div></article><article class='admin-panel'><div class='panel-title'><h2>Platform status</h2></div><div class='status-list'><div><strong>Primary site</strong><span>{esc(PRIMARY_DOMAIN)}</span></div><div><strong>Email notifications</strong><span>{'Enabled' if messaging.ENABLE_EMAIL else 'Disabled'}</span></div><div><strong>Admin login</strong><span>Username / password</span></div><div><strong>Database</strong><span>SQLite on EC2</span></div></div></article></section>
"""
        return html_response(self, 200, admin_layout('Dashboard', 'dashboard', content))

    def render_inbox(self, query: dict):
        status = query.get('status', [''])[0]
        q = query.get('q', [''])[0]
        tag = query.get('tag', [''])[0]
        convos = messaging.list_conversations(status=status, q=q, tag=tag)
        stats = messaging.inbox_stats()
        feedback_total = sum(stats['feedback'].values()) or 0
        happy = stats['feedback'].get('excellent', 0) + stats['feedback'].get('good', 0)
        score = round((happy / feedback_total) * 100) if feedback_total else 0
        rows = []
        for c in convos:
            feedback = f"<span class='feedback-chip'>{esc(rating_label(c['last_feedback_rating']))}</span>" if c['last_feedback_rating'] else ''
            rows.append(f"<a class='inbox-item priority-{esc(c['priority'])}' href='/admin/conversations/{esc(c['token'])}'><div><strong>{esc(c['subject'] or c['name'] or 'Visitor')}</strong><small>{esc(c['name'])} · {esc(c['email'])} · {esc(c['company'])}</small></div><div class='inbox-meta'><span class='badge status-{esc(c['status'])}'>{esc(status_label(c['status']))}</span><span>{esc(c['priority'])}</span>{feedback}<small>{esc(fmt_ts(c['updated_at']))}</small></div></a>")
        listing = ''.join(rows) or '<div class="admin-empty">No conversations match this filter.</div>'
        count_cards = ''.join(f"<a class='admin-stat-card compact' href='/admin/inbox?status={s}'><span>{status_label(s)}</span><strong>{stats['counts'].get(s, 0)}</strong></a>" for s in ['new','waiting_on_me','waiting_on_client','in_progress','closed'])
        content = admin_page_header('Inbox', 'Conversation inbox', 'Manage project requests, visitor chats, replies, internal notes, and feedback.', f"<a class='btn secondary' href='/admin/settings'>Settings</a>") + f"""
<section class='admin-stats compact'>{count_cards}<div class='admin-stat-card compact'><span>Satisfaction</span><strong>{score}%</strong></div></section>
<form class='admin-filter-bar' method='get'><input name='q' value='{esc(q)}' placeholder='Search name, email, company, subject, tags'><input name='tag' value='{esc(tag)}' placeholder='Filter tag'><button class='btn secondary' type='submit'>Search</button><a class='btn secondary' href='/admin/inbox'>Clear</a></form><section class='inbox-list'>{listing}</section>
"""
        return html_response(self, 200, admin_layout('Inbox', 'inbox', content))

    def render_admin_requests(self, query: dict):
        convos = [c for c in messaging.list_conversations(limit=200, q=query.get('q', [''])[0]) if c['kind'] == 'project_request']
        rows = ''.join(
            f"<a class='admin-list-row' href='/admin/conversations/{esc(c['token'])}'><div><strong>{esc(c['subject'] or 'Service request')}</strong><small>{esc(c['name'])} · {esc(c['company'])} · {esc(c['email'])}</small></div><span class='badge status-{esc(c['status'])}'>{esc(status_label(c['status']))}</span></a>"
            for c in convos
        ) or "<div class='admin-empty'>No service requests yet.</div>"
        content = admin_page_header('Requests', 'Service requests', 'Customer project and service requests from the public request form.', "<a class='btn secondary' href='/request'>Open public form</a>") + f"<section class='admin-panel'><div class='admin-list'>{rows}</div></section>"
        return html_response(self, 200, admin_layout('Service Requests', 'requests', content))

    def render_admin_leads(self, query: dict):
        convos = messaging.list_conversations(limit=200, q=query.get('q', [''])[0])
        seen = set()
        rows = []
        for c in convos:
            key = (c['email'] or c['name'] or c['token']).lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append(f"<div class='admin-list-row static'><div><strong>{esc(c['name'] or 'Visitor')}</strong><small>{esc(c['email'])} · {esc(c['company'])}</small></div><span>{esc(c['kind'].replace('_',' ').title())}</span></div>")
        listing = ''.join(rows) or "<div class='admin-empty'>No leads yet.</div>"
        content = admin_page_header('Leads', 'Lead list', 'People and companies that have contacted Mad Mallard Solutions.') + f"<section class='admin-panel'><div class='admin-list'>{listing}</div></section>"
        return html_response(self, 200, admin_layout('Leads', 'leads', content))

    def render_admin_sites(self):
        sites = load_sites()
        cards = []
        for site in sites:
            cards.append(f"""<article class='site-card'>
<div><span class='badge'>{esc(site.get('status'))}</span><h2>{esc(site.get('name'))}</h2><p>{esc(site.get('purpose'))}</p><p class='muted'>{esc(site.get('brand'))}</p></div>
<div class='site-card-footer'><strong>{esc(site.get('domain'))}</strong><span><a class='btn secondary small' href='/admin/sites/{esc(site.get('id'))}/edit'>Edit</a></span></div>
</article>""")
        content = admin_page_header('Sites', 'Managed sites', 'Shared platform, separate public identities. Each business can have its own domain, brand, and frontend.', "<a class='btn primary' href='/admin/sites/new'>Add site</a>") + f"<section class='site-grid'>{''.join(cards) or '<div class="admin-empty">No sites configured.</div>'}</section>"
        return html_response(self, 200, admin_layout('Sites', 'sites', content))

    def render_admin_site_form(self, site_id: str = ''):
        site = get_site(site_id) if site_id else None
        if site_id and not site:
            return html_response(self, 404, admin_layout('Site not found', 'sites', admin_page_header('Sites', 'Site not found', 'That managed site does not exist.', "<a class='btn secondary' href='/admin/sites'>Back</a>")))
        title = 'Edit site' if site else 'Add site'
        delete_button = f"<button class='btn danger' type='button' id='deleteSite'>Delete site</button>" if site else ''
        content = admin_page_header('Sites', title, 'Manage the public identity, domain, and brand notes for this site.', "<a class='btn secondary' href='/admin/sites'>Back to sites</a>") + f"""
<section class='admin-panel form-panel'>
<form id='siteForm' class='admin-form'>
<input type='hidden' name='id' value='{esc(site.get('id') if site else '')}'>
<label>Site name<input name='name' value='{esc(site.get('name') if site else '')}' required></label>
<label>Domain<input name='domain' value='{esc(site.get('domain') if site else '')}' required></label>
<label>Status<select name='status'>
{''.join(f"<option value='{esc(status)}' {'selected' if (site and site.get('status') == status) else ''}>{esc(status)}</option>" for status in ['Active','Planned','Draft','Paused'])}
</select></label>
<label>Purpose<textarea name='purpose' rows='4'>{esc(site.get('purpose') if site else '')}</textarea></label>
<label>Brand notes<textarea name='brand' rows='4'>{esc(site.get('brand') if site else '')}</textarea></label>
<div class='form-actions'><button class='btn primary' type='submit'>Save site</button>{delete_button}</div>
</form>
</section>
<script>
document.getElementById('siteForm').addEventListener('submit', async e=>{{e.preventDefault(); const data=Object.fromEntries(new FormData(e.target).entries()); const r=await fetch('/api/admin/sites/save',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}}); const out=await r.json(); if(out.ok) location.href=out.redirect; else alert(out.error || 'Save failed');}});
const del=document.getElementById('deleteSite'); if(del) del.addEventListener('click', async()=>{{if(!confirm('Delete this site?')) return; const id=document.querySelector('[name=id]').value; const r=await fetch('/api/admin/sites/delete',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{id}})}}); const out=await r.json(); if(out.ok) location.href=out.redirect; else alert(out.error || 'Delete failed');}});
</script>"""
        return html_response(self, 200, admin_layout(title, 'sites', content))

    def render_admin_crm(self, query: dict):
        convos = messaging.list_conversations(limit=300, q=query.get('q', [''])[0])
        contacts = {}
        for c in convos:
            key = (c['email'] or c['name'] or c['token']).lower()
            item = contacts.setdefault(key, {'name': c['name'] or 'Visitor', 'email': c['email'] or '', 'company': c['company'] or '', 'requests': 0, 'last': 0, 'tags': set(), 'token': c['token'], 'status': c['status']})
            item['requests'] += 1
            item['last'] = max(item['last'], int(c['updated_at'] or 0))
            item['status'] = c['status']
            item['token'] = c['token']
            for tag in (c['tags'] or '').split(','):
                if tag.strip():
                    item['tags'].add(tag.strip())
        rows = []
        for item in sorted(contacts.values(), key=lambda x: x['last'], reverse=True):
            tags = ' '.join(f"<span class='badge'>{esc(tag)}</span>" for tag in sorted(item['tags'])[:4])
            rows.append(f"<a class='admin-list-row crm-row' href='/admin/conversations/{esc(item['token'])}'><div><strong>{esc(item['name'])}</strong><small>{esc(item['email'])} · {esc(item['company'])}</small><div class='mini-tags'>{tags}</div></div><div class='inbox-meta'><span>{item['requests']} request{'s' if item['requests'] != 1 else ''}</span><span class='badge status-{esc(item['status'])}'>{esc(status_label(item['status']))}</span><small>{esc(fmt_ts(item['last']))}</small></div></a>")
        content = admin_page_header('CRM', 'Customer relationship manager', 'A lightweight view of contacts, companies, requests, tags, and recent activity.', "<a class='btn secondary' href='/admin/leads'>Lead list</a>") + f"""
<form class='admin-filter-bar simple' method='get'><input name='q' value='{esc(query.get('q', [''])[0])}' placeholder='Search contacts, companies, email, tags'><button class='btn secondary' type='submit'>Search</button><a class='btn secondary' href='/admin/crm'>Clear</a></form>
<section class='admin-panel'><div class='admin-list'>{''.join(rows) or '<div class="admin-empty">No CRM contacts yet.</div>'}</div></section>
"""
        return html_response(self, 200, admin_layout('CRM', 'crm', content))

    def render_admin_settings(self):
        content = admin_page_header('Settings', 'Platform settings', 'Current runtime and deployment configuration for this low-cost AWS-hosted platform.') + f"""
<section class='admin-grid two'><article class='admin-panel'><h2>Admin access</h2><div class='settings-list'><div><strong>Login mode</strong><span>Username / password</span></div><div><strong>Configured username</strong><span>{esc(ADMIN_USERNAME)}</span></div><div><strong>Session</strong><span>30-day signed cookie</span></div></div></article><article class='admin-panel'><h2>Email</h2><div class='settings-list'><div><strong>Notifications</strong><span>{'Enabled' if messaging.ENABLE_EMAIL else 'Disabled'}</span></div><div><strong>From</strong><span>{esc(messaging.NOTIFY_FROM or 'Not configured')}</span></div><div><strong>To</strong><span>{esc(messaging.NOTIFY_TO or 'Not configured')}</span></div></div></article><article class='admin-panel'><h2>Site</h2><div class='settings-list'><div><strong>Primary domain</strong><span>{esc(PRIMARY_DOMAIN)}</span></div><div><strong>Web server</strong><span>Caddy</span></div><div><strong>Database</strong><span>{esc(str(messaging.DB_PATH))}</span></div></div></article><article class='admin-panel'><h2>Notes</h2><p class='muted'>Settings are intentionally read-only here for now. Terraform remains the source of truth for infrastructure and sensitive values.</p></article></section>
"""
        return html_response(self, 200, admin_layout('Settings', 'settings', content))

    def render_admin_conversation(self, token: str):
        convo, messages = messaging.get_conversation(token)
        if not convo:
            return html_response(self, 404, '<h1>Conversation not found</h1>')
        rows = ''.join(f"<div class='msg {esc(m['sender_type'])}{' internal' if m['internal'] else ''}'><div class='msg-meta'><strong>{esc(m['sender'])}{' · internal note' if m['internal'] else ''}</strong><span>{esc(fmt_ts(m['created_at']))}</span></div><p>{esc(m['body'])}</p></div>" for m in messages)
        status_opts = ''.join(f"<option value='{s}' {'selected' if convo['status']==s else ''}>{status_label(s)}</option>" for s in messaging.STATUSES)
        pri_opts = ''.join(f"<option value='{p}' {'selected' if convo['priority']==p else ''}>{p.title()}</option>" for p in messaging.PRIORITIES)
        feedback_banner = f"<div class='feedback-card'><strong>Latest feedback:</strong> {esc(rating_label(convo['last_feedback_rating']))}</div>" if convo['last_feedback_rating'] else ''
        content = admin_page_header('Conversation', convo['subject'] or 'Conversation', f"{convo['name']} · {convo['email']} · {convo['company']}", "<a class='btn secondary' href='/admin/inbox'>Back to inbox</a>") + f"""{feedback_banner}<form id='metaForm' class='contact-panel compact'><label>Status<select name='status'>{status_opts}</select></label><label>Priority<select name='priority'>{pri_opts}</select></label><label>Tags<input name='tags' value='{esc(convo['tags'])}' placeholder='AWS, Terraform, Website'></label><button class='btn secondary' type='submit'>Save</button></form><section class='message-list'>{rows}</section><form id='replyForm' class='contact-panel'><textarea name='body' rows='5' placeholder='Reply to visitor or add internal note...' required></textarea><label class='check'><input type='checkbox' name='internal'> Internal note only</label><div class='saved-replies'><button type='button' data-template='Thanks for reaching out. I can help with this. Can you share a little more about your timeline and what you already have in place?'>/thanks</button><button type='button' data-template='For AWS/Terraform work, the next best step is usually a short discovery call so I can understand your current environment and constraints.'>/aws</button><button type='button' data-template='I received this and will take a closer look. I will follow up with next steps shortly.'>/received</button></div><button class='btn primary' type='submit'>Send</button></form><script>document.querySelectorAll('.saved-replies button').forEach(b=>b.addEventListener('click',()=>{{document.querySelector('#replyForm textarea').value=b.dataset.template;}}));document.getElementById('replyForm').addEventListener('submit', async e=>{{e.preventDefault(); const fd=new FormData(e.target); const data=Object.fromEntries(fd.entries()); data.internal=e.target.internal.checked; const r=await fetch('/api/admin/conversations/{token}/messages',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}}); if(r.ok) location.reload();}});document.getElementById('metaForm').addEventListener('submit', async e=>{{e.preventDefault(); const data=Object.fromEntries(new FormData(e.target).entries()); const r=await fetch('/api/admin/conversations/{token}/update',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}}); if(r.ok) location.reload();}});</script>"""
        return html_response(self, 200, admin_layout('Conversation', 'inbox', content))


if __name__ == '__main__':
    messaging.db()
    print(f'Mad Mallard Platform serving {PRIMARY_DOMAIN} on :8000', flush=True)
    ThreadingHTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
