#!/usr/bin/env python3
"""Patch site/solutions/server.py so protected admin URLs redirect to login with next=.

This intentionally edits the current working server.py in place instead of replacing it,
so existing admin dashboard/menu/site/CRM code is preserved.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "site" / "solutions" / "server.py"

if not SERVER.exists():
    print(f"ERROR: {SERVER} not found", file=sys.stderr)
    sys.exit(1)

text = SERVER.read_text(encoding="utf-8")
original = text

# Ensure quote is imported for next= URL encoding.
text = text.replace(
    "from urllib.parse import unquote, parse_qs, urlparse",
    "from urllib.parse import unquote, parse_qs, urlparse, quote",
)

# Add helper if missing.
if "def admin_login_location(" not in text:
    marker = "def admin_is_authenticated(handler: BaseHTTPRequestHandler, query: dict | None = None) -> bool:\n"
    helper = """
def admin_login_location(handler: BaseHTTPRequestHandler) -> str:
    parsed = urlparse(handler.path)
    next_url = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    if next_url in ["/admin/login", "/admin/logout"]:
        return "/admin/login"
    return f"/admin/login?next={quote(next_url, safe='')}"

"""
    if marker not in text:
        print("ERROR: could not find admin_is_authenticated marker", file=sys.stderr)
        sys.exit(1)
    text = text.replace(marker, helper + marker)

# Make require_admin redirect to login with next=.
text = text.replace(
    "redirect(handler, '/admin/login')\n        return False",
    "redirect(handler, admin_login_location(handler))\n        return False",
)

# Route /admin and /admin/ before static fallback. Prefer dashboard if present, inbox otherwise.
if "if path in ('/admin', '/admin/'):" not in text:
    anchor = "        if path == '/admin/login':\n"
    block = """        if path in ('/admin', '/admin/'):
            if not require_admin(self, query):
                return
            return redirect(self, '/admin/dashboard' if hasattr(self, 'render_admin_dashboard') else '/admin/inbox')
"""
    if anchor not in text:
        print("ERROR: could not find /admin/login GET route marker", file=sys.stderr)
        sys.exit(1)
    text = text.replace(anchor, block + anchor, 1)

# Pass query into render_login when possible.
text = text.replace(
    "if path == '/admin/login':\n            return self.render_login()",
    "if path == '/admin/login':\n            return self.render_login(query)",
)

# Update render_login signature.
text = text.replace("def render_login(self):", "def render_login(self, query: dict | None = None):")

# Add next handling in render_login body if missing.
if "next_url = (query or {}).get('next'" not in text:
    text = text.replace(
        "    def render_login(self, query: dict | None = None):\n",
        "    def render_login(self, query: dict | None = None):\n        next_url = (query or {}).get('next', [''])[0]\n        next_input = f\"<input type='hidden' name='next' value='{esc(next_url)}'>\" if next_url else ''\n",
    )

# Ensure the login form contains the hidden next field. This covers the common current template.
if "{next_input}<label>Username" not in text:
    text = text.replace(
        "<form method='post' action='/admin/login' class='contact-panel'><label>Username",
        "<form method='post' action='/admin/login' class='contact-panel'>{next_input}<label>Username",
    )
# If the login body is not an f-string yet, make the common triple-quoted assignment an f-string.
text = text.replace('body = """<!doctype html><html><head><title>Admin Login', 'body = f"""<!doctype html><html><head><title>Admin Login')

# Preserve next on successful login.
old_login = """if admin_auth_configured() and secrets.compare_digest(username, ADMIN_USERNAME) and verify_password(password, ADMIN_PASSWORD_HASH):
                session = make_admin_session(username)
                return redirect(self, '/admin/inbox', {'Set-Cookie': f'mms_admin_session={session}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000'})"""
new_login = """if admin_auth_configured() and secrets.compare_digest(username, ADMIN_USERNAME) and verify_password(password, ADMIN_PASSWORD_HASH):
                session = make_admin_session(username)
                next_url = str(payload.get('next', '')).strip()
                if not next_url.startswith('/admin') or next_url.startswith('/admin/login') or next_url.startswith('//'):
                    next_url = '/admin/dashboard' if hasattr(self, 'render_admin_dashboard') else '/admin/inbox'
                return redirect(self, next_url, {'Set-Cookie': f'mms_admin_session={session}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000'})"""
if old_login in text:
    text = text.replace(old_login, new_login)
elif "next_url = str(payload.get('next'" not in text:
    print("WARNING: could not patch login success redirect automatically; please inspect do_POST /admin/login", file=sys.stderr)

if text == original:
    print("No changes made; server.py may already be patched.")
else:
    SERVER.write_text(text, encoding="utf-8")
    print(f"Patched {SERVER}")
