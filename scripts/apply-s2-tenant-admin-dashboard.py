#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
server_path = ROOT / 'site/solutions/server.py'
source = server_path.read_text(encoding='utf-8')

replacements = [
    (
        'import tenant_conversations\n',
        'import tenant_conversations\nimport tenant_admin_dashboard\n',
    ),
    (
        "        ('/admin/sites', 'sites', 'Sites'),\n",
        "        ('/admin/tenants', 'tenants', 'Tenants'),\n        ('/admin/sites', 'sites', 'Sites'),\n",
    ),
    (
        "        if path == '/admin/sites/new':\n",
        "        if path == '/admin/tenants':\n"
        "            if not require_admin(self, query):\n"
        "                return\n"
        "            return self.render_admin_tenants()\n"
        "        if path == '/admin/sites/new':\n",
    ),
    (
        "        if parsed.path == '/api/admin/sites/save':\n",
        "        if parsed.path == '/api/admin/tenants/status':\n"
        "            query = parse_qs(parsed.query)\n"
        "            if not require_admin(self, query):\n"
        "                return\n"
        "            slug = str(payload.get('slug', '')).strip()\n"
        "            action = str(payload.get('action', '')).strip()\n"
        "            ok, message, result = tenant_admin_dashboard.change_status(slug, action)\n"
        "            return json_response(self, 200 if ok else 400, {\n"
        "                'ok': ok, 'message': message,\n"
        "                'status': result.current_status if result else '',\n"
        "            })\n"
        "        if parsed.path == '/api/admin/sites/save':\n",
    ),
    (
        "    def handle_admin_site_save(self, payload: dict):\n",
        "    def render_admin_tenants(self):\n"
        "        content = admin_page_header(\n"
        "            'Platform', 'Tenant administration',\n"
        "            'Review tenant status, domains, branding, users, and activity.'\n"
        "        ) + tenant_admin_dashboard.render_tenant_dashboard()\n"
        "        script = \"\"\"<script>document.querySelectorAll('[data-tenant-action]').forEach(button => {button.addEventListener('click', async () => {const action = button.dataset.tenantAction; const slug = button.dataset.tenant; if (!confirm(`${action} ${slug}?`)) return; const response = await fetch('/api/admin/tenants/status', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({slug, action})}); const result = await response.json(); if (!response.ok) {alert(result.message || 'Tenant update failed.'); return;} window.location.reload();});});</script>\"\"\"\n"
        "        return html_response(self, 200, admin_layout('Tenants', 'tenants', content + script))\n\n"
        "    def handle_admin_site_save(self, payload: dict):\n",
    ),
]

for old, new in replacements:
    if new in source:
        continue
    if old not in source:
        raise SystemExit(f'Expected server.py anchor not found: {old[:80]!r}')
    source = source.replace(old, new, 1)

server_path.write_text(source, encoding='utf-8')

changelog = ROOT / 'CHANGELOG.md'
text = changelog.read_text(encoding='utf-8')
entry = '- Tenant administration dashboard with tenant status, domain, branding, user, conversation, and project-request summaries.\n'
marker = '### Added\n'
if entry not in text:
    if marker not in text:
        raise SystemExit('CHANGELOG.md does not contain the expected Added section.')
    text = text.replace(marker, marker + '\n' + entry, 1)
    changelog.write_text(text, encoding='utf-8')

print('Applied S2-T13 tenant administration dashboard integration.')
