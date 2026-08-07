from odoo.tests.common import TransactionCase
from .settlement_test_helpers import SettlementTestFactory

class TestSettlementBilling(TransactionCase):
    def setUp(self):
        super().setUp()
        self.f = SettlementTestFactory(self.env)

    def test_01_create_document(self):
        doc = self.f.create_billing_doc(self.f.create_partner())
        self.assertTrue(doc.id)
        self.assertEqual(doc.state, 'draft')

    def test_02_create_line(self):
        doc = self.f.create_billing_doc(self.f.create_partner())
        line = self.f.create_billing_line(doc, amount=500.0)
        self.assertEqual(line.line_total, 500.0)
        self.assertEqual(line.amount_sign, 'positive')

    def test_03_external_reference_unique(self):
        partner = self.f.create_partner()
        currency = self.f.create_currency()
        doc1 = self.env['tlmp.carrier.billing.document'].create({
            'carrier_id': partner.id, 'currency_id': currency.id,
            'external_invoice_no': 'INV-001',
        })
        doc2 = self.env['tlmp.carrier.billing.document'].create({
            'carrier_id': partner.id, 'currency_id': currency.id,
            'external_invoice_no': 'INV-002',
        })
        self.assertNotEqual(doc1.external_invoice_no, doc2.external_invoice_no)
