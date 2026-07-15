#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / 'site/solutions/server.py'
TEST = ROOT / 'tests/test_sprint2_server_tenant_conversations.py'
CHANGELOG = ROOT / 'CHANGELOG.md'

text = SERVER.read_text(encoding='utf-8')

replacements = [
    (
        'import request_context\n',
        'import request_context\nimport tenant_conversations\n',
    ),
    (
        "        convo = messaging.create_conversation(kind='project_request', name=name, email=email, company=company, subject=subject, body=body, tags=[service] if service else [], lead={'service': service, 'timeline': timeline, 'budget': budget, 'message': message})",
        "        context = self.request_context()\n        if not context:\n            return json_response(self, 404, {'ok': False, 'error': 'Unknown tenant.'})\n        convo = tenant_conversations.create_conversation(tenant_slug=context.tenant.slug, kind='project_request', name=name, email=email, company=company, subject=subject, body=body, tags=[service] if service else [], lead={'service': service, 'timeline': timeline, 'budget': budget, 'message': message})",
    ),
    (
        "        convo = messaging.create_conversation(kind='chat', name=name, email=email, subject='Website chat', body=body, tags=['chat'])",
        "        context = self.request_context()\n        if not context:\n            return json_response(self, 404, {'ok': False, 'error': 'Unknown tenant.'})\n        convo = tenant_conversations.create_conversation(tenant_slug=context.tenant.slug, kind='chat', name=name, email=email, subject='Website chat', body=body, tags=['chat'])",
    ),
    (
        "        convo = messaging.add_message(token, body=body, sender=sender, sender_type='visitor')",
        "        context = self.request_context()\n        if not context:\n            return json_response(self, 404, {'ok': False, 'error': 'Unknown tenant.'})\n        convo = tenant_conversations.add_message(context.tenant.slug, token, body=body, sender=sender, sender_type='visitor')",
    ),
]

for old, new in replacements:
    if new in text:
        continue
    if old not in text:
        raise SystemExit(f'Expected server.py block not found:\n{old}')
    text = text.replace(old, new, 1)

SERVER.write_text(text, encoding='utf-8')

TEST.write_text('''from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / 'site/solutions/server.py'


class Sprint2ServerTenantConversationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SERVER.read_text(encoding='utf-8')

    def test_server_imports_tenant_conversations(self):
        self.assertIn('import tenant_conversations', self.source)

    def test_project_requests_use_resolved_tenant(self):
        self.assertIn(
            "tenant_conversations.create_conversation(tenant_slug=context.tenant.slug, kind='project_request'",
            self.source,
        )

    def test_chat_creation_uses_resolved_tenant(self):
        self.assertIn(
            "tenant_conversations.create_conversation(tenant_slug=context.tenant.slug, kind='chat'",
            self.source,
        )

    def test_visitor_message_write_uses_resolved_tenant(self):
        self.assertIn(
            "tenant_conversations.add_message(context.tenant.slug, token",
            self.source,
        )

    def test_public_conversation_writes_reject_unknown_tenant(self):
        self.assertGreaterEqual(
            self.source.count("return json_response(self, 404, {'ok': False, 'error': 'Unknown tenant.'})"),
            3,
        )

    def test_legacy_public_creation_calls_are_removed(self):
        self.assertNotIn("messaging.create_conversation(kind='project_request'", self.source)
        self.assertNotIn("messaging.create_conversation(kind='chat'", self.source)


if __name__ == '__main__':
    unittest.main()
''', encoding='utf-8')

changelog = CHANGELOG.read_text(encoding='utf-8')
entry = '- Public project requests, chats, and visitor replies now persist within the resolved tenant.\n'
marker = '### Added\n\n'
if entry not in changelog:
    if marker not in changelog:
        raise SystemExit('CHANGELOG Added section not found')
    changelog = changelog.replace(marker, marker + entry, 1)
    CHANGELOG.write_text(changelog, encoding='utf-8')

print('Applied S2-T05 tenant-scoped public conversation integration.')
