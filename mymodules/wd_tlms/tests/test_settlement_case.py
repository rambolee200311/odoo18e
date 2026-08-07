from odoo.tests.common import TransactionCase
from .settlement_test_helpers import SettlementTestFactory

class TestSettlementCase(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Case = self.env['tlmp.carrier.settlement.case']

    def test_40_manual_create_resolve_close(self):
        c = self.Case.create({'case_type': 'amount_discrepancy', 'source': 'manual'})
        self.assertEqual(c.state, 'open')
        c.action_process()
        c.action_resolve()
        c.action_close()
        self.assertEqual(c.state, 'closed')

    def test_41_cancel_and_reopen(self):
        c = self.Case.create({'case_type': 'unmatched', 'source': 'auto_matching'})
        c.action_cancel()
        self.assertEqual(c.state, 'cancelled')
