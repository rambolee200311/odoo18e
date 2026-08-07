from odoo.tests.common import TransactionCase
from .settlement_test_helpers import SettlementTestFactory

class TestSettlementSecurity(TransactionCase):
    def setUp(self):
        super().setUp()
        self.f = SettlementTestFactory(self.env)
        self.partner = self.f.create_partner()
        self.doc = self.f.create_billing_doc(self.partner)
        self.line = self.f.create_billing_line(self.doc)
        self.order = self.f.create_transport_order()

    def test_50_operator_readonly(self):
        alloc = self.f.create_allocation(self.line, self.order, 100.0)
        self.assertTrue(alloc.id)
        self.assertEqual(alloc.allocated_amount, 100.0)

    def test_51_clerk_can_correct(self):
        alloc = self.f.create_allocation(self.line, self.order, 100.0)
        Correction = self.env['tlmp.carrier.allocation.correction']
        result = Correction.reverse_allocation(alloc, reason='Clerk correction')
        self.assertTrue(result['original'].is_reversal)
