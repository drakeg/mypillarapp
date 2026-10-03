from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SOLUTIONS = Path(__file__).resolve().parents[1] / 'site' / 'solutions'
if str(SOLUTIONS) not in sys.path:
    sys.path.insert(0, str(SOLUTIONS))

import crm_companies
import crm_contacts
import crm_opportunities
import crm_quotes
import tenant_auth


class Sprint4CrmQuoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        tenant_auth.DATA_DIR = Path(self.temp.name)
        tenant_auth.DB_PATH = tenant_auth.DATA_DIR / 'madmallard.sqlite3'

    def tearDown(self):
        self.temp.cleanup()

    def test_quote_line_totals_are_deterministic_integer_cents(self):
        quote = crm_quotes.create_quote('solutions', title='Migration estimate')
        line1 = crm_quotes.add_line(
            'solutions', quote.id, description='Planning', quantity=2,
            unit_price_cents=12500, position=2
        )
        line2 = crm_quotes.add_line(
            'solutions', quote.id, description='Implementation', quantity=3,
            unit_price_cents=20000, position=1
        )
        self.assertEqual(25000, line1.line_total_cents)
        self.assertEqual(60000, line2.line_total_cents)
        self.assertEqual(['Implementation', 'Planning'],
                         [l.description for l in crm_quotes.list_lines('solutions', quote.id)])
        self.assertEqual(85000, crm_quotes.get_quote('solutions', quote.id).subtotal_cents)

    def test_quote_relationships_are_tenant_safe(self):
        foreign = crm_companies.create_company('adventures', name='Foreign')
        with self.assertRaises(ValueError):
            crm_quotes.create_quote('solutions', title='Blocked', company_id=foreign.id)

    def test_quote_relationship_consistency(self):
        first = crm_companies.create_company('solutions', name='First')
        second = crm_companies.create_company('solutions', name='Second')
        contact = crm_contacts.create_contact('solutions', name='Jane', company_id=first.id)
        with self.assertRaises(ValueError):
            crm_quotes.create_quote(
                'solutions', title='Mismatch', company_id=second.id, contact_id=contact.id
            )
        opp = crm_opportunities.create_opportunity(
            'solutions', title='Deal', company_id=first.id, contact_id=contact.id
        )
        with self.assertRaises(ValueError):
            crm_quotes.create_quote(
                'solutions', title='Mismatch', company_id=second.id,
                contact_id=contact.id, opportunity_id=opp.id
            )

    def test_only_draft_quotes_accept_new_lines(self):
        quote = crm_quotes.create_quote('solutions', title='Estimate')
        sent = crm_quotes.set_quote_status('solutions', quote.id, 'sent')
        self.assertEqual('sent', sent.status)
        with self.assertRaises(ValueError):
            crm_quotes.add_line('solutions', quote.id, description='Too late', unit_price_cents=100)

    def test_archived_quote_is_immutable(self):
        quote = crm_quotes.create_quote('solutions', title='Old quote')
        archived = crm_quotes.set_quote_status('solutions', quote.id, 'archived')
        self.assertEqual('archived', archived.status)
        with self.assertRaises(ValueError):
            crm_quotes.set_quote_status('solutions', quote.id, 'draft')

    def test_validation(self):
        with self.assertRaises(ValueError):
            crm_quotes.create_quote('solutions', title='')
        with self.assertRaises(ValueError):
            crm_quotes.create_quote('solutions', title='Bad currency', currency='US')
        with self.assertRaises(ValueError):
            crm_quotes.create_quote('solutions', title='Bad date', valid_until='12/31/2026')
        quote = crm_quotes.create_quote('solutions', title='Valid')
        for kwargs in (
            {'description':'', 'quantity':1, 'unit_price_cents':0},
            {'description':'x', 'quantity':0, 'unit_price_cents':0},
            {'description':'x', 'quantity':1, 'unit_price_cents':-1},
            {'description':'x', 'quantity':1, 'unit_price_cents':0, 'position':-1},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    crm_quotes.add_line('solutions', quote.id, **kwargs)

    def test_cross_tenant_reads_and_line_writes_do_not_leak(self):
        quote = crm_quotes.create_quote('solutions', title='Private')
        self.assertIsNone(crm_quotes.get_quote('adventures', quote.id))
        self.assertEqual([], crm_quotes.list_lines('adventures', quote.id))
        with self.assertRaises(ValueError):
            crm_quotes.add_line('adventures', quote.id, description='Blocked')

    def test_suspended_tenant_cannot_use_quotes(self):
        quote = crm_quotes.create_quote('solutions', title='Before suspension')
        with tenant_auth.db() as conn:
            conn.execute("UPDATE auth_organizations SET status='suspended' WHERE slug='solutions'")
            conn.commit()
        with self.assertRaises(ValueError):
            crm_quotes.get_quote('solutions', quote.id)


if __name__ == '__main__':
    unittest.main()
