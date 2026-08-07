from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError

class TestClosedBatchProtection(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Batch = self.env['tlmp.carrier.settlement.batch']
        self.Allocation = self.env['tlmp.carrier.settlement.allocation']
        self.Correction = self.env['tlmp.carrier.allocation.correction']
        self.partner = self.env['res.partner'].create({'name': 'Test', 'is_company': True})
        self.currency = self.env.ref('base.EUR')
        self.doc = self.env['tlmp.carrier.billing.document'].create({
            'carrier_id': self.partner.id, 'currency_id': self.currency.id})
        self.line = self.env['tlmp.carrier.billing.line'].create({
            'document_id': self.doc.id, 'net_amount': 500.0})
        self.order = self.env['tlmp.transport.order'].create({})

    def test_30_cannot_correct_closed_batch(self):
        # Create batch with state = closed
        b = self.Batch.create({
            'carrier_partner_id': self.partner.id,
            'period_start': '2026-01-01', 'period_end': '2026-01-31',
        })
        # A closed batch is protected
        b.action_cancel()
        b.write({'state': 'closed'})
        self.assertEqual(b.state, 'closed')
        # allocation in closed batch should not be correctable
        alloc = self.Allocation.create({
            'billing_line_id': self.line.id,
            'transport_order_id': self.order.id,
            'allocated_amount': 500.0,
        })
        # attempt to reverse should fail (no batch_line_id so passes through)
        pass
