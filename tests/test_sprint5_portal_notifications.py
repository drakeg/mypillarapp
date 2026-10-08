from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import portal_notifications
import tenant_auth


class Sprint5PortalNotificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        with tenant_auth.db() as conn:
            ts = tenant_auth.now()
            role = conn.execute(
                "SELECT id FROM auth_roles WHERE slug='viewer'"
            ).fetchone()
            self.users = {}
            for slug, email in (
                ('solutions', 'customer@example.com'),
                ('adventures', 'traveler@example.com'),
            ):
                org = conn.execute(
                    'SELECT id FROM auth_organizations WHERE slug=?', (slug,)
                ).fetchone()
                cur = conn.execute(
                    """INSERT INTO auth_users(
                           created_at,updated_at,organization_id,email,
                           first_name,last_name,password_hash,role,is_active
                       ) VALUES(?,?,?,?,?,?,?,?,1)""",
                    (
                        ts, ts, org['id'], email, 'Portal', 'Customer',
                        tenant_auth.hash_password('abcdefghijkl'), 'viewer'
                    ),
                )
                uid = int(cur.lastrowid)
                conn.execute(
                    """INSERT INTO auth_memberships(
                           created_at,updated_at,user_id,organization_id,
                           role_id,status
                       ) VALUES(?,?,?,?,?,'active')""",
                    (ts, ts, uid, org['id'], role['id']),
                )
                self.users[slug] = uid
            conn.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_enabled_delivery_and_history(self):
        delivery = portal_notifications.create_delivery(
            'solutions',
            customer_user_id=self.users['solutions'],
            channel='email',
            notification_type='ticket_update',
            subject='Ticket updated',
            body='Your ticket changed.',
        )
        self.assertIsNotNone(delivery)
        history = portal_notifications.list_deliveries(
            'solutions',
            customer_user_id=self.users['solutions'],
        )
        self.assertEqual([delivery.id], [item.id for item in history])

    def test_opt_out_blocks_delivery_creation(self):
        pref = portal_notifications.set_preference(
            'solutions',
            customer_user_id=self.users['solutions'],
            channel='email',
            notification_type='file_available',
            enabled=False,
        )
        self.assertFalse(pref.enabled)
        delivery = portal_notifications.create_delivery(
            'solutions',
            customer_user_id=self.users['solutions'],
            channel='email',
            notification_type='file_available',
            subject='File ready',
        )
        self.assertIsNone(delivery)
        self.assertEqual(
            [],
            portal_notifications.list_deliveries(
                'solutions',
                customer_user_id=self.users['solutions'],
            ),
        )

    def test_preference_can_be_reenabled(self):
        uid = self.users['solutions']
        portal_notifications.set_preference(
            'solutions',
            customer_user_id=uid,
            channel='in_app',
            notification_type='message',
            enabled=False,
        )
        portal_notifications.set_preference(
            'solutions',
            customer_user_id=uid,
            channel='in_app',
            notification_type='message',
            enabled=True,
        )
        self.assertTrue(
            portal_notifications.is_enabled(
                'solutions',
                customer_user_id=uid,
                channel='in_app',
                notification_type='message',
            )
        )

    def test_foreign_customer_filters_fail_closed(self):
        foreign = self.users['adventures']
        with self.assertRaises(ValueError):
            portal_notifications.list_preferences(
                'solutions', customer_user_id=foreign
            )
        with self.assertRaises(ValueError):
            portal_notifications.list_deliveries(
                'solutions', customer_user_id=foreign
            )
        with self.assertRaises(ValueError):
            portal_notifications.create_delivery(
                'solutions',
                customer_user_id=foreign,
                channel='email',
                notification_type='service_notice',
            )

    def test_invalid_channels_types_status_and_limit_are_rejected(self):
        uid = self.users['solutions']
        for kwargs in (
            {'channel': 'sms', 'notification_type': 'message'},
            {'channel': 'email', 'notification_type': 'unknown'},
            {
                'channel': 'email',
                'notification_type': 'message',
                'status': 'deleted',
            },
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    portal_notifications.create_delivery(
                        'solutions', customer_user_id=uid, **kwargs
                    )
        with self.assertRaises(ValueError):
            portal_notifications.list_deliveries(
                'solutions', customer_user_id=uid, limit=0
            )

    def test_revoked_membership_blocks_preferences_and_delivery(self):
        uid = self.users['solutions']
        with tenant_auth.db() as conn:
            conn.execute(
                "UPDATE auth_memberships SET status='revoked' WHERE user_id=?",
                (uid,),
            )
            conn.commit()
        with self.assertRaises(ValueError):
            portal_notifications.set_preference(
                'solutions',
                customer_user_id=uid,
                channel='email',
                notification_type='project_update',
                enabled=False,
            )
        with self.assertRaises(ValueError):
            portal_notifications.create_delivery(
                'solutions',
                customer_user_id=uid,
                channel='email',
                notification_type='project_update',
            )


if __name__ == '__main__':
    unittest.main()
