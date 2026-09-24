from pathlib import Path
import ast
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / 'site' / 'solutions' / 'server.py'


class Sprint2LegacySessionReadTests(unittest.TestCase):
    def test_server_does_not_call_legacy_current_user(self):
        tree = ast.parse(SERVER_PATH.read_text(encoding='utf-8'))
        legacy_calls = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr != 'current_user':
                continue
            owner = func.value
            if isinstance(owner, ast.Name) and owner.id == 'tenant_auth':
                legacy_calls.append(node.lineno)
        self.assertEqual(
            legacy_calls,
            [],
            f'server.py must use request context/current_user_for_tenant; legacy calls at {legacy_calls}',
        )


if __name__ == '__main__':
    unittest.main()
