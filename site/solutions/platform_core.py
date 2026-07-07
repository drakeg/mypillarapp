from __future__ import annotations

from pathlib import Path
import json
import sqlite3
import time
from typing import Any

DATA_DIR = Path('/data')
DB_PATH = DATA_DIR / 'madmallard.sqlite3'

DEFAULT_ORGS = [
    {
        'slug': 'solutions',
        'name': 'Mad Mallard Solutions',
        'legal_name': 'Mad Mallard Solutions',
        'business_type': 'IT consulting / cloud services',
        'public_domain': 'pillar.madmallards.com',
        'brand_color': '#36d1dc',
        'status': 'active',
        'enabled_modules': ['dashboard', 'messaging', 'forms', 'crm', 'projects'],
        'notes': 'Technology, cloud, Linux, automation, and small business consulting.',
    },
    {
        'slug': 'personal-training',
        'name': 'Mad Mallard Personal Training',
        'legal_name': 'Mad Mallard Personal Training',
        'business_type': 'Fitness / coaching',
        'public_domain': '',
        'brand_color': '#a78bfa',
        'status': 'draft',
        'enabled_modules': ['dashboard', 'messaging', 'forms', 'crm'],
        'notes': 'Future fitness coaching, client intake, programming, and appointments.',
    },
    {
        'slug': 'adventures',
        'name': 'Mad Mallards Adventures',
        'legal_name': 'Mad Mallards Adventures',
        'business_type': 'RV travel / creator business',
        'public_domain': '',
        'brand_color': '#22c55e',
        'status': 'draft',
        'enabled_modules': ['dashboard', 'messaging', 'forms', 'content', 'sponsors'],
        'notes': 'Future creator hub, sponsors, affiliate links, content planning, and media kit.',
    },
]

MODULES = {
    'dashboard': 'Dashboard',
    'messaging': 'Messaging',
    'forms': 'Forms',
    'crm': 'CRM',
    'projects': 'Projects',
    'tasks': 'Tasks',
    'files': 'Files',
    'calendar': 'Calendar',
    'content': 'Content',
    'sponsors': 'Sponsors',
    'estimates': 'Estimates',
    'invoices': 'Invoices',
}


def now() -> int:
    return int(time.time())


def db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('''
        CREATE TABLE IF NOT EXISTS organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            legal_name TEXT,
            business_type TEXT,
            public_domain TEXT,
            brand_color TEXT NOT NULL DEFAULT '#36d1dc',
            status TEXT NOT NULL DEFAULT 'draft',
            enabled_modules TEXT NOT NULL DEFAULT '[]',
            settings_json TEXT NOT NULL DEFAULT '{}',
            notes TEXT NOT NULL DEFAULT ''
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS organization_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'owner',
            created_at INTEGER NOT NULL,
            UNIQUE(organization_id, username),
            FOREIGN KEY(organization_id) REFERENCES organizations(id)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at INTEGER NOT NULL,
            actor TEXT NOT NULL,
            organization_id INTEGER,
            action TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(organization_id) REFERENCES organizations(id)
        )
    ''')
    conn.commit()
    seed_defaults(conn)
    return conn


def _modules_json(value: list[str] | str | None) -> str:
    if value is None:
        value = []
    if isinstance(value, str):
        parts = [part.strip() for part in value.replace('\n', ',').split(',')]
    else:
        parts = [str(part).strip() for part in value]
    clean = []
    for part in parts:
        if part and part in MODULES and part not in clean:
            clean.append(part)
    return json.dumps(clean)


def parse_modules(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or '[]')
        if isinstance(value, list):
            return [str(v) for v in value if str(v) in MODULES]
    except Exception:
        pass
    return []


def seed_defaults(conn: sqlite3.Connection) -> None:
    ts = now()
    for org in DEFAULT_ORGS:
        existing = conn.execute('SELECT id FROM organizations WHERE slug = ?', (org['slug'],)).fetchone()
        if existing:
            continue
        cur = conn.execute(
            '''INSERT INTO organizations(created_at, updated_at, slug, name, legal_name, business_type, public_domain, brand_color, status, enabled_modules, settings_json, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?)''',
            (ts, ts, org['slug'], org['name'], org['legal_name'], org['business_type'], org['public_domain'], org['brand_color'], org['status'], _modules_json(org['enabled_modules']), org['notes']),
        )
        org_id = cur.lastrowid
        conn.execute('INSERT OR IGNORE INTO organization_members(organization_id, username, role, created_at) VALUES (?, ?, ?, ?)', (org_id, 'greg', 'owner', ts))
        conn.execute('INSERT INTO audit_events(created_at, actor, organization_id, action, detail) VALUES (?, ?, ?, ?, ?)', (ts, 'system', org_id, 'organization.created', 'Default organization seeded'))
    conn.commit()


def list_organizations() -> list[sqlite3.Row]:
    with db() as conn:
        return conn.execute('SELECT * FROM organizations ORDER BY name').fetchall()


def get_organization(slug: str) -> sqlite3.Row | None:
    with db() as conn:
        return conn.execute('SELECT * FROM organizations WHERE slug = ?', (slug,)).fetchone()


def update_organization(slug: str, *, actor: str, name: str, legal_name: str, business_type: str, public_domain: str, brand_color: str, status: str, enabled_modules: list[str] | str, notes: str) -> bool:
    status = status if status in ['active', 'draft', 'archived'] else 'draft'
    brand_color = brand_color.strip() or '#36d1dc'
    ts = now()
    with db() as conn:
        row = conn.execute('SELECT id FROM organizations WHERE slug = ?', (slug,)).fetchone()
        if not row:
            return False
        conn.execute(
            '''UPDATE organizations
               SET updated_at = ?, name = ?, legal_name = ?, business_type = ?, public_domain = ?, brand_color = ?, status = ?, enabled_modules = ?, notes = ?
               WHERE slug = ?''',
            (ts, name.strip(), legal_name.strip(), business_type.strip(), public_domain.strip(), brand_color, status, _modules_json(enabled_modules), notes.strip(), slug),
        )
        conn.execute('INSERT INTO audit_events(created_at, actor, organization_id, action, detail) VALUES (?, ?, ?, ?, ?)', (ts, actor or 'admin', row['id'], 'organization.updated', 'Organization settings updated'))
        conn.commit()
        return True


def dashboard_summary() -> dict[str, Any]:
    with db() as conn:
        orgs = conn.execute('SELECT * FROM organizations ORDER BY name').fetchall()
        conversations = conn.execute('SELECT status, priority, tags FROM conversations').fetchall() if _table_exists(conn, 'conversations') else []
        messages = conn.execute('SELECT COUNT(*) AS c FROM messages').fetchone()['c'] if _table_exists(conn, 'messages') else 0
        audit = conn.execute('SELECT * FROM audit_events ORDER BY id DESC LIMIT 8').fetchall()
    status_counts: dict[str, int] = {}
    priority_counts: dict[str, int] = {}
    for c in conversations:
        status_counts[c['status']] = status_counts.get(c['status'], 0) + 1
        priority_counts[c['priority']] = priority_counts.get(c['priority'], 0) + 1
    return {
        'organizations': orgs,
        'conversation_count': len(conversations),
        'message_count': messages,
        'status_counts': status_counts,
        'priority_counts': priority_counts,
        'audit': audit,
    }


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None
