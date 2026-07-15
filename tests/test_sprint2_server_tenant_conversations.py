from pathlib import Path
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
