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
import messaging

ROOT = Path('/app').resolve()
INDEX = ROOT / 'index.html'
ADMIN_TOKEN = os.environ.get('MADMALLARD_ADMIN_TOKEN', '').strip()
PRIMARY_DOMAIN = os.environ.get('MADMALLARD_PRIMARY_DOMAIN', 'pillar.madmallards.com')

FORM_CONFIG = {
    'services': ['AWS / cloud setup','Linux server support','Terraform / infrastructure as code','Docker / deployment help','Automation / scripting','Small business website','Not sure yet'],
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
            return json_response(self, 200, FORM_CONFIG)
        if path.startswith('/chat/'):
            return self.render_chat(path.rstrip('/').split('/')[-1])
        if path.startswith('/feedback/'):
            parts = path.strip('/').split('/')
            if len(parts) >= 3:
                return self.render_feedback(parts[1], parts[2])
        if path == '/admin/login':
            return self.render_login()
        if path == '/admin/logout':
            return html_response(self, 200, '<h1>Signed out</h1><p><a href="/admin/login">Sign in again</a></p>', {'Set-Cookie': 'mms_admin=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax'})
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
        body = """<!doctype html><html><head><title>Admin Login - Mad Mallard Solutions</title><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='/assets/styles.css'></head>
<body class='conversation-page'><main class='conversation-shell'><h1>Admin login</h1><p>Enter the admin token once. This browser will remember it for 30 days.</p><form method='post' action='/admin/login' class='contact-panel'><label>Admin token<input type='password' name='token' autocomplete='current-password' required autofocus></label><button class='btn primary' type='submit'>Open inbox</button></form></main></body></html>"""
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
