from pathlib import Path

root = Path(__file__).resolve().parents[1]
auth_path = root / 'site' / 'solutions' / 'tenant_auth.py'
server_path = root / 'site' / 'solutions' / 'server.py'
changelog_path = root / 'CHANGELOG.md'
test_path = root / 'tests' / 'test_sprint2_tenant_user_identities.py'

auth = auth_path.read_text()
auth = auth.replace('email TEXT NOT NULL UNIQUE COLLATE NOCASE,', 'email TEXT NOT NULL COLLATE NOCASE,', 1)

index_anchor = "    conn.execute('CREATE INDEX IF NOT EXISTS idx_auth_tokens_lookup ON auth_tokens(token_hash, purpose, expires_at)')"
if index_anchor not in auth:
    raise SystemExit('index anchor not found')
auth = auth.replace(index_anchor, "    _migrate_auth_users_email_scope(conn)\n    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_users_org_email ON auth_users(organization_id, email COLLATE NOCASE)')\n" + index_anchor, 1)

migration = '''\n\ndef _migrate_auth_users_email_scope(conn: sqlite3.Connection) -> None:\n    indexes = conn.execute("PRAGMA index_list(auth_users)").fetchall()\n    for index in indexes:\n        if not index['unique']:\n            continue\n        columns = conn.execute(f"PRAGMA index_info({index['name']})").fetchall()\n        if [column['name'] for column in columns] != ['email']:\n            continue\n        conn.execute('PRAGMA foreign_keys = OFF')\n        conn.execute('ALTER TABLE auth_users RENAME TO auth_users_legacy')\n        conn.execute(\"\"\"CREATE TABLE auth_users (\n            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,\n            organization_id INTEGER NOT NULL, email TEXT NOT NULL COLLATE NOCASE,\n            first_name TEXT NOT NULL DEFAULT '', last_name TEXT NOT NULL DEFAULT '', password_hash TEXT NOT NULL,\n            role TEXT NOT NULL DEFAULT 'viewer', is_active INTEGER NOT NULL DEFAULT 0,\n            email_verified_at INTEGER, last_login_at INTEGER,\n            FOREIGN KEY(organization_id) REFERENCES auth_organizations(id))\"\"\")\n        conn.execute(\"\"\"INSERT INTO auth_users SELECT id, created_at, updated_at, organization_id, email, first_name,\n            last_name, password_hash, role, is_active, email_verified_at, last_login_at FROM auth_users_legacy\"\"\")\n        conn.execute('DROP TABLE auth_users_legacy')\n        conn.execute('PRAGMA foreign_keys = ON')\n        break\n'''
auth = auth.replace('\n\ndef seed_organizations(conn: sqlite3.Connection) -> None:\n', migration + '\n\ndef seed_organizations(conn: sqlite3.Connection) -> None:\n', 1)

auth = auth.replace("existing = conn.execute('SELECT id FROM auth_users WHERE lower(email) = lower(?)', (email,)).fetchone()", "existing = conn.execute('SELECT id FROM auth_users WHERE organization_id = ? AND lower(email) = lower(?)', (org['id'], email)).fetchone()", 1)
auth = auth.replace("def login_user(email: str, password: str) -> tuple[bool, str, str]:", "def login_user(email: str, password: str, organization_slug: str = 'solutions') -> tuple[bool, str, str]:", 1)
auth = auth.replace("user = conn.execute('SELECT * FROM auth_users WHERE lower(email) = lower(?)', (email,)).fetchone()", "user = conn.execute('''SELECT u.* FROM auth_users u JOIN auth_organizations o ON o.id = u.organization_id WHERE o.slug = ? AND lower(u.email) = lower(?)''', (organization_slug, email)).fetchone()", 1)
auth = auth.replace("duplicate = conn.execute('SELECT id FROM auth_users WHERE lower(email)=lower(?) AND id<>?', (email, user_id)).fetchone()", "duplicate = conn.execute('''SELECT other.id FROM auth_users other JOIN auth_users current ON current.id = ? WHERE other.organization_id = current.organization_id AND lower(other.email)=lower(?) AND other.id<>current.id''', (user_id, email)).fetchone()", 1)
auth_path.write_text(auth)

server = server_path.read_text()
old = """            ok, message, session = tenant_auth.login_user(
                str(payload.get('email', '')),
                str(payload.get('password', '')),
            )
"""
new = """            ok, message, session = tenant_auth.login_user(
                str(payload.get('email', '')),
                str(payload.get('password', '')),
                context.tenant.slug,
            )
"""
if old not in server:
    raise SystemExit('server login anchor not found')
server_path.write_text(server.replace(old, new, 1))

changelog = changelog_path.read_text()
entry = '- Customer account email uniqueness and login resolution are now scoped to the active tenant.\n'
if entry not in changelog:
    changelog = changelog.replace('### Added\n\n', '### Added\n\n' + entry, 1)
changelog_path.write_text(changelog)

test_path.write_text('''from pathlib import Path
import importlib, sys, tempfile, unittest
SITE_DIR = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
sys.path.insert(0, str(SITE_DIR)) if str(SITE_DIR) not in sys.path else None
import messaging, tenant_auth

class Sprint2TenantUserIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); data = Path(self.tmp.name)
        messaging.DATA_DIR = data; messaging.DB_PATH = data / 'madmallard.sqlite3'
        tenant_auth.DATA_DIR = data; tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        importlib.reload(tenant_auth); messaging.send_email = lambda *a, **k: True
    def tearDown(self): self.tmp.cleanup()
    def register(self, tenant, email, password):
        return tenant_auth.register_user(organization_slug=tenant, first_name='Test', last_name='User', email=email, password=password, public_host=f'{tenant}.example.com')
    def activate(self):
        with tenant_auth.db() as conn: conn.execute('UPDATE auth_users SET is_active=1'); conn.commit()
    def test_same_email_can_register_in_two_tenants(self):
        self.assertTrue(self.register('solutions','shared@example.com','SolutionsPass123!')[0])
        self.assertTrue(self.register('adventures','shared@example.com','AdventurePass123!')[0])
    def test_duplicate_email_is_rejected_within_tenant(self):
        self.assertTrue(self.register('solutions','same@example.com','FirstPassword123!')[0])
        self.assertFalse(self.register('solutions','same@example.com','SecondPassword123!')[0])
    def test_login_is_tenant_scoped(self):
        self.register('solutions','shared@example.com','SolutionsPass123!'); self.register('adventures','shared@example.com','AdventurePass123!'); self.activate()
        self.assertTrue(tenant_auth.login_user('shared@example.com','SolutionsPass123!','solutions')[0])
        self.assertFalse(tenant_auth.login_user('shared@example.com','SolutionsPass123!','adventures')[0])
        self.assertTrue(tenant_auth.login_user('shared@example.com','AdventurePass123!','adventures')[0])
    def test_profile_uniqueness_is_tenant_scoped(self):
        self.register('solutions','one@example.com','SolutionsPass123!'); self.register('adventures','target@example.com','AdventurePass123!')
        with tenant_auth.db() as conn: user = conn.execute("SELECT u.id FROM auth_users u JOIN auth_organizations o ON o.id=u.organization_id WHERE o.slug='solutions'").fetchone()
        self.assertTrue(tenant_auth.update_profile(user['id'],'Test','User','target@example.com')[0])
    def test_composite_unique_index_exists(self):
        with tenant_auth.db() as conn:
            indexes = conn.execute('PRAGMA index_list(auth_users)').fetchall(); unique=[]
            for idx in indexes:
                if idx['unique']: unique.append([c['name'] for c in conn.execute(f"PRAGMA index_info({idx['name']})").fetchall()])
        self.assertIn(['organization_id','email'], unique); self.assertNotIn(['email'], unique)

if __name__ == '__main__': unittest.main()
''')
print('Applied S2-T08 tenant-scoped user identities.')
