from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import billing_plans
import tenant_auth
import tenant_sites


class Sprint8PlanEntitlementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        tenant_auth.DATA_DIR = data
        tenant_auth.DB_PATH = data / 'madmallard.sqlite3'
        tenant_sites.ensure_schema()
        self.owner = self._user('solutions', 'owner@example.com', 'owner')
        self.admin = self._user('solutions', 'admin@example.com', 'admin')
        self.staff = self._user('solutions', 'staff@example.com', 'staff')
        self.other_owner = self._user('adventures', 'other@example.com', 'owner')

    def tearDown(self):
        self.tmp.cleanup()

    def _user(self, organization_slug, email, role):
        with tenant_auth.db() as conn:
            org = conn.execute(
                'SELECT id FROM auth_organizations WHERE slug=?',
                (organization_slug,),
            ).fetchone()
            role_row = conn.execute(
                'SELECT id FROM auth_roles WHERE slug=?',
                (role,),
            ).fetchone()
            now = tenant_auth.now()
            cur = conn.execute(
                '''INSERT INTO auth_users(
                       created_at,updated_at,organization_id,email,
                       first_name,last_name,password_hash,role,is_active
                   ) VALUES(?,?,?,?,?,?,?,?,1)''',
                (
                    now, now, org['id'], email, 'Plan', 'User',
                    tenant_auth.hash_password('abcdefghijkl'), role,
                ),
            )
            user_id = int(cur.lastrowid)
            conn.execute(
                '''INSERT INTO auth_memberships(
                       created_at,updated_at,user_id,organization_id,
                       role_id,status
                   ) VALUES(?,?,?,?,?,'active')''',
                (now, now, user_id, org['id'], role_row['id']),
            )
            conn.commit()
        return user_id

    def _starter(self):
        return billing_plans.create_plan(
            self.owner,
            'solutions',
            slug='starter',
            name='Starter',
            entitlements={
                'sites': 2,
                'crm': True,
                'portal': True,
                'creator': False,
                'ai': False,
                'ai_rolling_units': 0,
            },
        )

    def test_plan_is_tenant_owned_and_stable(self):
        plan = self._starter()
        self.assertEqual('solutions', plan.organization_slug)
        self.assertEqual('starter', plan.slug)
        self.assertEqual(2, plan.entitlements['sites'])
        self.assertTrue(plan.entitlements['crm'])

        self.assertIsNone(
            billing_plans.get_plan('adventures', 'starter')
        )

    def test_cross_tenant_same_slug_is_isolated(self):
        self._starter()
        other = billing_plans.create_plan(
            self.other_owner,
            'adventures',
            slug='starter',
            name='Adventure Starter',
            entitlements={'sites': 1, 'creator': True},
        )
        self.assertEqual('adventures', other.organization_slug)
        self.assertNotEqual(
            billing_plans.get_plan('solutions', 'starter').id,
            other.id,
        )

    def test_staff_cannot_create_or_assign_plans(self):
        with self.assertRaises(PermissionError):
            billing_plans.create_plan(
                self.staff,
                'solutions',
                slug='staff-plan',
                name='Staff',
                entitlements={},
            )
        self._starter()
        with self.assertRaises(PermissionError):
            billing_plans.assign_plan(
                self.staff, 'solutions', 'starter'
            )

    def test_assignment_is_explicit_and_same_tenant(self):
        plan = self._starter()
        assignment = billing_plans.assign_plan(
            self.admin, 'solutions', 'starter'
        )
        self.assertEqual(plan.id, assignment.plan_id)
        self.assertEqual('solutions', assignment.organization_slug)

        billing_plans.create_plan(
            self.other_owner,
            'adventures',
            slug='foreign',
            name='Foreign',
            entitlements={'sites': 1},
        )
        with self.assertRaises(ValueError):
            billing_plans.assign_plan(
                self.owner, 'solutions', 'foreign'
            )

    def test_unassigned_internal_tenant_preserves_existing_features(self):
        for key in ('crm', 'portal', 'creator', 'ai'):
            decision = billing_plans.entitlement('solutions', key)
            self.assertTrue(decision.allowed)
            self.assertEqual('internal_default', decision.source)
            self.assertIsNone(decision.plan_slug)

        sites = billing_plans.entitlement('solutions', 'sites')
        self.assertTrue(sites.allowed)
        self.assertIsNone(sites.quota)

    def test_assigned_plan_is_deterministic_without_provider_state(self):
        self._starter()
        billing_plans.assign_plan(
            self.owner, 'solutions', 'starter'
        )
        crm = billing_plans.entitlement('solutions', 'crm')
        creator = billing_plans.entitlement('solutions', 'creator')
        sites = billing_plans.entitlement('solutions', 'sites')

        self.assertTrue(crm.allowed)
        self.assertFalse(creator.allowed)
        self.assertEqual(2, sites.quota)
        self.assertEqual('plan', sites.source)
        self.assertEqual('starter', sites.plan_slug)

    def test_unknown_entitlement_fails_closed(self):
        with self.assertRaises(PermissionError):
            billing_plans.entitlement('solutions', 'unknown-feature')

    def test_quota_enforcement_is_server_side(self):
        self._starter()
        billing_plans.assign_plan(
            self.owner, 'solutions', 'starter'
        )
        billing_plans.require_entitlement(
            'solutions', 'sites', requested_units=2
        )
        with self.assertRaises(PermissionError):
            billing_plans.require_entitlement(
                'solutions', 'sites', requested_units=3
            )
        with self.assertRaises(PermissionError):
            billing_plans.require_entitlement(
                'solutions', 'creator'
            )

    def test_plan_entitlement_validation_is_bounded(self):
        with self.assertRaises(ValueError):
            billing_plans.create_plan(
                self.owner,
                'solutions',
                slug='bad',
                name='Bad',
                entitlements={'mystery': True},
            )
        with self.assertRaises(ValueError):
            billing_plans.create_plan(
                self.owner,
                'solutions',
                slug='too-large',
                name='Too Large',
                entitlements={
                    'sites': billing_plans.MAX_QUOTA + 1,
                },
            )

    def test_assigned_plan_cannot_be_archived(self):
        self._starter()
        billing_plans.assign_plan(
            self.owner, 'solutions', 'starter'
        )
        with self.assertRaises(ValueError):
            billing_plans.archive_plan(
                self.owner, 'solutions', 'starter'
            )


if __name__ == '__main__':
    unittest.main()
