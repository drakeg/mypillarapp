from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SOLUTIONS_DIR = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
sys.path.insert(0, str(SOLUTIONS_DIR))

import messaging  # noqa: E402
import tenant_auth  # noqa: E402


class Sprint1RegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        database = data_dir / 'madmallard.sqlite3'

        tenant_auth.DATA_DIR = data_dir
        tenant_auth.DB_PATH = database
        messaging.DATA_DIR = data_dir
        messaging.DB_PATH = database

        with tenant_auth.db():
            pass
        with messaging.db():
            pass

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_active_user(
        self,
        email: str = 'customer@example.com',
        password: str = 'CorrectHorseBattery1!',
    ) -> int:
        with patch.object(messaging, 'send_email', return_value=True):
            ok, message = tenant_auth.register_user(
                organization_slug='solutions',
                first_name='Test',
                last_name='Customer',
                email=email,
                password=password,
            )
        self.assertTrue(ok, message)
        with tenant_auth.db() as conn:
            row = conn.execute(
                'SELECT id FROM auth_users WHERE email = ?', (email,)
            ).fetchone()
            self.assertIsNotNone(row)
            user_id = int(row['id'])
            conn.execute(
                '''UPDATE auth_users
                   SET is_active = 1, email_verified_at = ?, updated_at = ?
                   WHERE id = ?''',
                (tenant_auth.now(), tenant_auth.now(), user_id),
            )
            conn.commit()
        return user_id

    def _create_conversation(
        self,
        email: str,
        token: str,
        kind: str = 'chat',
        subject: str = 'Website chat',
    ) -> int:
        timestamp = tenant_auth.now()
        with messaging.db() as conn:
            cursor = conn.execute(
                '''INSERT INTO conversations(
                       created_at, updated_at, token, kind, subject, name,
                       email, company, status, priority, tags, lead_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, '', 'new', 'normal', '', '{}')''',
                (
                    timestamp,
                    timestamp,
                    token,
                    kind,
                    subject,
                    'Test Customer',
                    email,
                ),
            )
            conversation_id = int(cursor.lastrowid)
            conn.execute(
                '''INSERT INTO messages(
                       conversation_id, created_at, sender_type, sender, body,
                       internal
                   ) VALUES (?, ?, 'visitor', 'Customer', 'First message', 0)''',
                (conversation_id, timestamp),
            )
            conn.execute(
                '''INSERT INTO messages(
                       conversation_id, created_at, sender_type, sender, body,
                       internal
                   ) VALUES (?, ?, 'admin', 'Admin', 'Internal secret', 1)''',
                (conversation_id, timestamp + 1),
            )
            conn.execute(
                '''INSERT INTO messages(
                       conversation_id, created_at, sender_type, sender, body,
                       internal
                   ) VALUES (?, ?, 'admin', 'Admin', 'Public reply', 0)''',
                (conversation_id, timestamp + 2),
            )
            conn.commit()
        return conversation_id

    def test_password_hash_round_trip_and_wrong_password(self) -> None:
        encoded = tenant_auth.hash_password('CorrectHorseBattery1!')
        self.assertTrue(
            tenant_auth.verify_password('CorrectHorseBattery1!', encoded)
        )
        self.assertFalse(tenant_auth.verify_password('wrong-password', encoded))
        self.assertFalse(tenant_auth.verify_password('anything', 'invalid'))

    def test_registration_rejects_duplicate_email(self) -> None:
        self._create_active_user()
        with patch.object(messaging, 'send_email', return_value=True):
            ok, message = tenant_auth.register_user(
                organization_slug='solutions',
                first_name='Other',
                last_name='Customer',
                email='CUSTOMER@example.com',
                password='AnotherStrongPassword1!',
            )
        self.assertFalse(ok)
        self.assertIn('already exists', message)

    def test_login_current_user_and_logout(self) -> None:
        self._create_active_user()
        ok, message, session = tenant_auth.login_user(
            'customer@example.com', 'CorrectHorseBattery1!'
        )
        self.assertTrue(ok, message)
        self.assertTrue(session)

        user = tenant_auth.current_user(session)
        self.assertIsNotNone(user)
        self.assertEqual('customer@example.com', user['email'])
        self.assertEqual('Mad Mallard Solutions', user['organization_name'])

        tenant_auth.logout_session(session)
        self.assertIsNone(tenant_auth.current_user(session))

    def test_profile_update_enforces_unique_email(self) -> None:
        first_id = self._create_active_user('first@example.com')
        self._create_active_user('second@example.com')

        ok, message = tenant_auth.update_profile(
            first_id, 'Updated', 'Customer', 'second@example.com'
        )
        self.assertFalse(ok)
        self.assertIn('already uses', message)

        ok, message = tenant_auth.update_profile(
            first_id, 'Updated', 'Customer', 'updated@example.com'
        )
        self.assertTrue(ok, message)
        with tenant_auth.db() as conn:
            row = conn.execute(
                'SELECT first_name, email FROM auth_users WHERE id = ?',
                (first_id,),
            ).fetchone()
        self.assertEqual('Updated', row['first_name'])
        self.assertEqual('updated@example.com', row['email'])

    def test_password_change_invalidates_all_customer_sessions(self) -> None:
        user_id = self._create_active_user()
        first = tenant_auth.login_user(
            'customer@example.com', 'CorrectHorseBattery1!'
        )[2]
        second = tenant_auth.login_user(
            'customer@example.com', 'CorrectHorseBattery1!'
        )[2]
        self.assertIsNotNone(tenant_auth.current_user(first))
        self.assertIsNotNone(tenant_auth.current_user(second))

        ok, message = tenant_auth.change_password(
            user_id,
            'CorrectHorseBattery1!',
            'ReplacementPassword2!',
        )
        self.assertTrue(ok, message)
        self.assertIsNone(tenant_auth.current_user(first))
        self.assertIsNone(tenant_auth.current_user(second))
        self.assertFalse(
            tenant_auth.login_user(
                'customer@example.com', 'CorrectHorseBattery1!'
            )[0]
        )
        self.assertTrue(
            tenant_auth.login_user(
                'customer@example.com', 'ReplacementPassword2!'
            )[0]
        )

    def test_customer_history_is_scoped_by_email_and_kind(self) -> None:
        self._create_active_user()
        self._create_conversation(
            'customer@example.com', 'owned-chat', 'chat', 'Owned chat'
        )
        self._create_conversation(
            'customer@example.com',
            'owned-request',
            'project_request',
            'Owned request',
        )
        self._create_conversation(
            'other@example.com', 'other-chat', 'chat', 'Other customer chat'
        )

        session = tenant_auth.login_user(
            'customer@example.com', 'CorrectHorseBattery1!'
        )[2]
        user = tenant_auth.current_user(session)
        chats = tenant_auth._customer_history(user, 'chat')
        requests = tenant_auth._customer_history(user, 'project_request')

        self.assertEqual(['owned-chat'], [row['token'] for row in chats])
        self.assertEqual(['owned-request'], [row['token'] for row in requests])

    def test_customer_cannot_open_another_customers_conversation(self) -> None:
        self._create_active_user()
        self._create_conversation(
            'customer@example.com', 'owned-chat', 'chat', 'Owned chat'
        )
        self._create_conversation(
            'other@example.com', 'other-chat', 'chat', 'Other chat'
        )

        session = tenant_auth.login_user(
            'customer@example.com', 'CorrectHorseBattery1!'
        )[2]
        user = tenant_auth.current_user(session)

        owned_html = tenant_auth.render_customer_conversation(user, 'owned-chat')
        denied_html = tenant_auth.render_customer_conversation(user, 'other-chat')

        self.assertIsNotNone(owned_html)
        self.assertIsNone(denied_html)
        self.assertIn('First message', owned_html)
        self.assertIn('Public reply', owned_html)
        self.assertNotIn('Internal secret', owned_html)

    def test_dashboard_counts_project_requests_and_chats(self) -> None:
        self._create_active_user()
        self._create_conversation(
            'customer@example.com', 'chat-one', 'chat', 'Chat one'
        )
        self._create_conversation(
            'customer@example.com',
            'request-one',
            'project_request',
            'Request one',
        )

        session = tenant_auth.login_user(
            'customer@example.com', 'CorrectHorseBattery1!'
        )[2]
        user = tenant_auth.current_user(session)
        counts, recent = tenant_auth._customer_activity(user)

        self.assertEqual(2, counts['total'])
        self.assertEqual(2, counts['open'])
        self.assertEqual(1, counts['requests'])
        self.assertEqual(1, counts['conversations'])
        self.assertEqual(2, len(recent))


if __name__ == '__main__':
    unittest.main()
