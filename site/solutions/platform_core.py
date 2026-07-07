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

# --- CRM foundation -------------------------------------------------------
CRM_STATUSES = ['lead', 'prospect', 'customer', 'vendor', 'archived']
LEAD_STATUSES = ['new', 'contacted', 'qualified', 'proposal', 'won', 'lost']


def ensure_crm_schema(conn: sqlite3.Connection | None = None) -> None:
    close = False
    if conn is None:
        conn = db()
        close = True
    conn.execute('''
        CREATE TABLE IF NOT EXISTS crm_companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            organization_slug TEXT NOT NULL DEFAULT 'solutions',
            name TEXT NOT NULL,
            website TEXT NOT NULL DEFAULT '',
            industry TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'prospect',
            notes TEXT NOT NULL DEFAULT ''
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS crm_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            organization_slug TEXT NOT NULL DEFAULT 'solutions',
            company_id INTEGER,
            name TEXT NOT NULL,
            email TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'lead',
            tags TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(company_id) REFERENCES crm_companies(id)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS crm_leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            organization_slug TEXT NOT NULL DEFAULT 'solutions',
            contact_id INTEGER,
            company_id INTEGER,
            source TEXT NOT NULL DEFAULT 'manual',
            title TEXT NOT NULL,
            value_estimate TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'new',
            priority TEXT NOT NULL DEFAULT 'normal',
            notes TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(contact_id) REFERENCES crm_contacts(id),
            FOREIGN KEY(company_id) REFERENCES crm_companies(id)
        )
    ''')
    conn.commit()
    if close:
        conn.close()


def crm_summary() -> dict[str, Any]:
    with db() as conn:
        ensure_crm_schema(conn)
        companies = conn.execute('SELECT COUNT(*) AS c FROM crm_companies').fetchone()['c']
        contacts = conn.execute('SELECT COUNT(*) AS c FROM crm_contacts').fetchone()['c']
        leads = conn.execute('SELECT COUNT(*) AS c FROM crm_leads').fetchone()['c']
        open_leads = conn.execute("SELECT COUNT(*) AS c FROM crm_leads WHERE status NOT IN ('won','lost')").fetchone()['c']
        recent_contacts = conn.execute('''SELECT c.*, co.name AS company_name FROM crm_contacts c LEFT JOIN crm_companies co ON co.id = c.company_id ORDER BY c.updated_at DESC, c.id DESC LIMIT 8''').fetchall()
        recent_leads = conn.execute('''SELECT l.*, c.name AS contact_name, co.name AS company_name FROM crm_leads l LEFT JOIN crm_contacts c ON c.id = l.contact_id LEFT JOIN crm_companies co ON co.id = l.company_id ORDER BY l.updated_at DESC, l.id DESC LIMIT 8''').fetchall()
    return {'companies': companies, 'contacts': contacts, 'leads': leads, 'open_leads': open_leads, 'recent_contacts': recent_contacts, 'recent_leads': recent_leads}


def crm_list_companies() -> list[sqlite3.Row]:
    with db() as conn:
        ensure_crm_schema(conn)
        return conn.execute('SELECT * FROM crm_companies ORDER BY name').fetchall()


def crm_list_contacts() -> list[sqlite3.Row]:
    with db() as conn:
        ensure_crm_schema(conn)
        return conn.execute('''SELECT c.*, co.name AS company_name FROM crm_contacts c LEFT JOIN crm_companies co ON co.id = c.company_id ORDER BY c.updated_at DESC, c.id DESC''').fetchall()


def crm_list_leads() -> list[sqlite3.Row]:
    with db() as conn:
        ensure_crm_schema(conn)
        return conn.execute('''SELECT l.*, c.name AS contact_name, co.name AS company_name FROM crm_leads l LEFT JOIN crm_contacts c ON c.id = l.contact_id LEFT JOIN crm_companies co ON co.id = l.company_id ORDER BY l.updated_at DESC, l.id DESC''').fetchall()


def crm_create_company(*, actor: str, name: str, website: str = '', industry: str = '', status: str = 'prospect', notes: str = '', organization_slug: str = 'solutions') -> int:
    ts = now()
    status = status if status in CRM_STATUSES else 'prospect'
    with db() as conn:
        ensure_crm_schema(conn)
        cur = conn.execute('''INSERT INTO crm_companies(created_at, updated_at, organization_slug, name, website, industry, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (ts, ts, organization_slug, name.strip(), website.strip(), industry.strip(), status, notes.strip()))
        conn.execute('INSERT INTO audit_events(created_at, actor, action, detail) VALUES (?, ?, ?, ?)', (ts, actor or 'admin', 'crm.company.created', name.strip()))
        conn.commit()
        return int(cur.lastrowid)


def crm_create_contact(*, actor: str, name: str, email: str = '', phone: str = '', title: str = '', company_id: str | int | None = None, status: str = 'lead', tags: str = '', notes: str = '', organization_slug: str = 'solutions') -> int:
    ts = now()
    status = status if status in CRM_STATUSES else 'lead'
    cid = int(company_id) if str(company_id or '').isdigit() else None
    with db() as conn:
        ensure_crm_schema(conn)
        cur = conn.execute('''INSERT INTO crm_contacts(created_at, updated_at, organization_slug, company_id, name, email, phone, title, status, tags, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (ts, ts, organization_slug, cid, name.strip(), email.strip(), phone.strip(), title.strip(), status, tags.strip(), notes.strip()))
        conn.execute('INSERT INTO audit_events(created_at, actor, action, detail) VALUES (?, ?, ?, ?)', (ts, actor or 'admin', 'crm.contact.created', name.strip()))
        conn.commit()
        return int(cur.lastrowid)


def crm_create_lead(*, actor: str, title: str, contact_id: str | int | None = None, company_id: str | int | None = None, source: str = 'manual', value_estimate: str = '', status: str = 'new', priority: str = 'normal', notes: str = '', organization_slug: str = 'solutions') -> int:
    ts = now()
    status = status if status in LEAD_STATUSES else 'new'
    priority = priority if priority in ['low', 'normal', 'high', 'urgent'] else 'normal'
    contact = int(contact_id) if str(contact_id or '').isdigit() else None
    company = int(company_id) if str(company_id or '').isdigit() else None
    with db() as conn:
        ensure_crm_schema(conn)
        cur = conn.execute('''INSERT INTO crm_leads(created_at, updated_at, organization_slug, contact_id, company_id, source, title, value_estimate, status, priority, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (ts, ts, organization_slug, contact, company, source.strip(), title.strip(), value_estimate.strip(), status, priority, notes.strip()))
        conn.execute('INSERT INTO audit_events(created_at, actor, action, detail) VALUES (?, ?, ?, ?)', (ts, actor or 'admin', 'crm.lead.created', title.strip()))
        conn.commit()
        return int(cur.lastrowid)
