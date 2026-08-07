from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError

class TestAllocationReversal(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Correction = self.env['tlmp.carrier.allocation.correction']
        self.Allocation = self.env['tlmp.carrier.settlement.allocation']
        self.History = self.env['tlmp.carrier.matching.history']
        self.partner = self.env['res.partner'].create({'name': 'Test', 'is_company': True})
        self.currency = self.env.ref('base.EUR')
        self.doc = self.env['tlmp.carrier.billing.document'].create({
            'carrier_id': self.partner.id, 'currency_id': self.currency.id})
        self.line = self.env['tlmp.carrier.billing.line'].create({
            'document_id': self.doc.id, 'net_amount': 500.0})
        self.order = self.env['tlmp.transport.order'].create({})

    def test_10_reverse_allocation(self):
        alloc = self.Allocation.create({
            'billing_line_id': self.line.id,
            'transport_order_id': self.order.id,
            'allocated_amount': 500.0,
        })
        result = self.Correction.reverse_allocation(alloc, reason='Test reversal')
        self.assertTrue(result['original'].is_reversal)
        self.assertTrue(result['replacement'])
        self.assertEqual(result['replacement'].reversed_allocation_id.id, alloc.id)

    def test_11_cannot_reverse_reversal(self):
        alloc = self.Allocation.create({
            'billing_line_id': self.line.id,
            'transport_order_id': self.order.id,
            'allocated_amount': 500.0,
        })
        self.Correction.reverse_allocation(alloc, reason='First')
        with self.assertRaises(Exception):
            self.Correction.reverse_allocation(alloc, reason='Second')

    def test_12_history_recorded(self):
        alloc = self.Allocation.create({
            'billing_line_id': self.line.id,
            'transport_order_id': self.order.id,
            'allocated_amount': 500.0,
        })
        self.Correction.reverse_allocation(alloc, reason='Test audit')
        history = self.History.search([('operation', '=', 'allocation_reversed')])
        self.assertTrue(history)
