from odoo.tests.common import TransactionCase
from .settlement_test_helpers import SettlementTestFactory

class TestSettlementConsistency(TransactionCase):
    def setUp(self):
        super().setUp()
        self.f = SettlementTestFactory(self.env)

    def test_60_billing_allocation_balance(self):
        partner = self.f.create_partner()
        doc = self.f.create_billing_doc(partner)
        ct = self.f.create_charge_type()
        line = self.f.create_billing_line(doc, amount=1000.0)
        order = self.f.create_transport_order()
        alloc = self.f.create_allocation(line, order, 600.0)
        remaining = line.line_total - alloc.allocated_amount
        self.assertEqual(remaining, 400.0)

    def test_61_batch_aggregated_total(self):
        partner = self.f.create_partner()
        batch = self.f.create_batch(partner)
        doc = self.f.create_billing_doc(partner)
        line = self.f.create_billing_line(doc, amount=500.0)
        order = self.f.create_transport_order()
        alloc = self.f.create_allocation(line, order, 500.0)
        self.env['tlmp.carrier.settlement.batch.line'].create({
            'batch_id': batch.id, 'billing_document_id': doc.id,
            'billing_line_id': line.id, 'snapshot_amount': 500.0,
        })
        self.assertEqual(batch.aggregated_total, 500.0)

    def test_62_correction_chain_consistent(self):
        partner = self.f.create_partner()
        doc = self.f.create_billing_doc(partner)
        ct = self.f.create_charge_type()
        line = self.f.create_billing_line(doc, amount=500.0)
        order = self.f.create_transport_order()
        alloc = self.f.create_allocation(line, order, 500.0)
        Correction = self.env['tlmp.carrier.allocation.correction']
        result = Correction.reverse_allocation(alloc, reason='Test')
        new_alloc = result['replacement']
        self.assertEqual(alloc.allocated_amount, 500.0)
        self.assertEqual(new_alloc.allocated_amount, 0.0)
