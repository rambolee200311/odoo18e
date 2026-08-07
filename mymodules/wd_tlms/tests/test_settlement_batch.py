from odoo.tests.common import TransactionCase
from .settlement_test_helpers import SettlementTestFactory

class TestSettlementBatch(TransactionCase):
    def setUp(self):
        super().setUp()
        self.f = SettlementTestFactory(self.env)
        self.partner = self.f.create_partner()
        self.batch = self.f.create_batch(self.partner)

    def test_30_batch_lifecycle(self):
        self.batch.action_submit()
        self.assertEqual(self.batch.state, 'submitted')
        self.batch.action_approve()
        self.assertEqual(self.batch.state, 'approved')
        self.batch.action_close()
        self.assertEqual(self.batch.state, 'closed')

    def test_31_closed_batch_protection(self):
        self.batch.action_close()
        self.assertEqual(self.batch.state, 'closed')

    def test_32_batch_total_consistency(self):
        doc = self.f.create_billing_doc(self.partner)
        line = self.f.create_billing_line(doc, amount=300.0)
        order = self.f.create_transport_order()
        alloc = self.f.create_allocation(line, order, 300.0)
        batch_line = self.env['tlmp.carrier.settlement.batch.line'].create({
            'batch_id': self.batch.id,
            'billing_document_id': doc.id,
            'billing_line_id': line.id,
            'snapshot_amount': 300.0,
        })
        self.assertEqual(self.batch.aggregated_total, 300.0)
