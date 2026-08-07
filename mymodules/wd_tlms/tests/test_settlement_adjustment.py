from odoo.tests.common import TransactionCase

class TestSettlementAdjustment(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Adjust = self.env['tlmp.carrier.settlement.adjustment']
        self.partner = self.env['res.partner'].create({'name': 'Test Carrier', 'is_company': True})
        self.currency = self.env.ref('base.EUR')

    def test_01_create_adjustment(self):
        a = self.Adjust.create({
            'type': 'carrier_credit',
            'carrier_partner_id': self.partner.id,
            'amount': 500.0,
            'currency_id': self.currency.id,
            'reason': 'Test adjustment',
        })
        self.assertTrue(a.id)
        self.assertEqual(a.state, 'draft')

    def test_02_approve_adjustment(self):
        a = self.Adjust.create({
            'type': 'carrier_debit', 'carrier_partner_id': self.partner.id,
            'amount': 300.0, 'currency_id': self.currency.id,
        })
        a.action_approve()
        self.assertEqual(a.state, 'approved')
        self.assertTrue(a.approved_by)

    def test_03_cancel_adjustment(self):
        a = self.Adjust.create({
            'type': 'carrier_credit', 'carrier_partner_id': self.partner.id,
            'amount': 200.0, 'currency_id': self.currency.id,
        })
        a.action_cancel()
        self.assertEqual(a.state, 'cancelled')
