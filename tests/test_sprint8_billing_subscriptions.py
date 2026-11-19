from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import billing_plans
import billing_subscriptions
import tenant_auth
import tenant_sites


class Sprint8SubscriptionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()
        self.owner = self._user('solutions', 'owner@example.com', 'owner')
        self.staff = self._user('solutions', 'staff@example.com', 'staff')
        self.other_owner = self._user('adventures', 'other@example.com', 'owner')
        billing_plans.create_plan(
            self.owner,'solutions',slug='starter',name='Starter',
            entitlements={'sites':2,'crm':True}
        )
        billing_plans.create_plan(
            self.other_owner,'adventures',slug='starter',name='Adventure Starter',
            entitlements={'sites':1,'creator':True}
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _user(self, org_slug, email, role):
        with tenant_auth.db() as conn:
            org=conn.execute('SELECT id FROM auth_organizations WHERE slug=?',(org_slug,)).fetchone()
            role_row=conn.execute('SELECT id FROM auth_roles WHERE slug=?',(role,)).fetchone()
            now=tenant_auth.now()
            cur=conn.execute(
                '''INSERT INTO auth_users(created_at,updated_at,organization_id,email,
                first_name,last_name,password_hash,role,is_active)
                VALUES(?,?,?,?,?,?,?,?,1)''',
                (now,now,org['id'],email,'Sub','User',tenant_auth.hash_password('abcdefghijkl'),role)
            )
            uid=int(cur.lastrowid)
            conn.execute(
                '''INSERT INTO auth_memberships(created_at,updated_at,user_id,organization_id,role_id,status)
                VALUES(?,?,?,?,?,'active')''',
                (now,now,uid,org['id'],role_row['id'])
            )
            conn.commit()
        return uid

    def test_create_trialing_subscription_and_history(self):
        sub=billing_subscriptions.create_subscription(
            self.owner,'solutions',plan_slug='starter',status='trialing'
        )
        self.assertEqual('trialing',sub.status)
        self.assertEqual('solutions',sub.organization_slug)
        self.assertEqual('starter',sub.plan_slug)
        history=billing_subscriptions.list_transitions('solutions',sub.id)
        self.assertEqual(1,len(history))
        self.assertEqual('trialing',history[0].to_status)

    def test_same_tenant_plan_required(self):
        with self.assertRaises(ValueError):
            billing_subscriptions.create_subscription(
                self.owner,'solutions',plan_slug='foreign'
            )

    def test_staff_cannot_administer_subscription(self):
        with self.assertRaises(PermissionError):
            billing_subscriptions.create_subscription(
                self.staff,'solutions',plan_slug='starter'
            )

    def test_deterministic_transition_rules(self):
        sub=billing_subscriptions.create_subscription(
            self.owner,'solutions',plan_slug='starter',status='trialing'
        )
        sub=billing_subscriptions.transition_subscription(
            self.owner,'solutions',sub.id,'active',reason='trial complete'
        )
        self.assertEqual('active',sub.status)
        sub=billing_subscriptions.transition_subscription(
            self.owner,'solutions',sub.id,'past_due'
        )
        self.assertEqual('past_due',sub.status)
        sub=billing_subscriptions.transition_subscription(
            self.owner,'solutions',sub.id,'active'
        )
        self.assertEqual('active',sub.status)

    def test_invalid_transition_fails_closed(self):
        sub=billing_subscriptions.create_subscription(
            self.owner,'solutions',plan_slug='starter',status='active'
        )
        with self.assertRaises(ValueError):
            billing_subscriptions.transition_subscription(
                self.owner,'solutions',sub.id,'trialing'
            )

    def test_cancel_is_terminal_and_preserves_plan_assignment(self):
        billing_plans.assign_plan(self.owner,'solutions','starter')
        sub=billing_subscriptions.create_subscription(
            self.owner,'solutions',plan_slug='starter',status='active'
        )
        canceled=billing_subscriptions.transition_subscription(
            self.owner,'solutions',sub.id,'canceled',reason='customer request'
        )
        self.assertEqual('canceled',canceled.status)
        self.assertIsNotNone(canceled.canceled_at)
        self.assertIsNotNone(billing_plans.get_assignment('solutions'))
        with self.assertRaises(ValueError):
            billing_subscriptions.transition_subscription(
                self.owner,'solutions',sub.id,'active'
            )

    def test_only_one_current_subscription_per_tenant(self):
        billing_subscriptions.create_subscription(
            self.owner,'solutions',plan_slug='starter',status='active'
        )
        with self.assertRaises(ValueError):
            billing_subscriptions.create_subscription(
                self.owner,'solutions',plan_slug='starter',status='trialing'
            )

    def test_new_subscription_allowed_after_cancel(self):
        sub=billing_subscriptions.create_subscription(
            self.owner,'solutions',plan_slug='starter',status='active'
        )
        billing_subscriptions.transition_subscription(
            self.owner,'solutions',sub.id,'canceled'
        )
        new=billing_subscriptions.create_subscription(
            self.owner,'solutions',plan_slug='starter',status='trialing'
        )
        self.assertNotEqual(sub.id,new.id)

    def test_provider_references_are_optional_and_bounded(self):
        sub=billing_subscriptions.create_subscription(
            self.owner,'solutions',plan_slug='starter',
            provider_customer_ref='cus_123',
            provider_subscription_ref='sub_123'
        )
        self.assertEqual('cus_123',sub.provider_customer_ref)
        self.assertEqual('sub_123',sub.provider_subscription_ref)
        with self.assertRaises(ValueError):
            billing_subscriptions.create_subscription(
                self.other_owner,'adventures',plan_slug='starter',
                provider_customer_ref='x'*256
            )

    def test_cross_tenant_subscription_lookup_fails_closed(self):
        sub=billing_subscriptions.create_subscription(
            self.owner,'solutions',plan_slug='starter'
        )
        self.assertIsNone(
            billing_subscriptions.get_subscription('adventures',sub.id)
        )


if __name__ == '__main__':
    unittest.main()
