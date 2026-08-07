from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from .settlement_test_helpers import SettlementTestFactory

class TestSettlementAllocation(TransactionCase):
    def setUp(self):
        super().setUp()
        self.f = SettlementTestFactory(self.env)
        self.partner = self.f.create_partner()
        self.doc = self.f.create_billing_doc(self.partner)
        self.ct = self.f.create_charge_type()
        self.line = self.f.create_billing_line(self.doc, amount=500.0)
        self.order = self.f.create_transport_order()

    def test_20_allocation_never_exceeds_billing(self):
        alloc = self.f.create_allocation(self.line, self.order, 300.0)
        self.assertLessEqual(alloc.allocated_amount, self.line.line_total)

    def test_21_allocation_exceeds_raises(self):
        with self.assertRaises(Exception):
            self.f.create_allocation(self.line, self.order, 600.0)

    def test_22_reverse_replacement_preserves_history(self):
        alloc = self.f.create_allocation(self.line, self.order, 200.0)
        Correction = self.env['tlmp.carrier.allocation.correction']
        result = Correction.reverse_allocation(alloc, reason='Test correction')
        self.assertTrue(result['original'].is_reversal)
        self.assertTrue(result['replacement'].reversed_allocation_id)
        history = self.env['tlmp.carrier.matching.history'].search([
            ('operation', '=', 'allocation_reversed'),
        ])
        self.assertTrue(history)
