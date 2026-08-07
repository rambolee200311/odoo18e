from odoo.tests.common import TransactionCase

class TestBatchApproval(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Batch = self.env['tlmp.carrier.settlement.batch']
        self.History = self.env['tlmp.carrier.settlement.batch.approval.history']
        self.partner = self.env['res.partner'].create({'name': 'Test', 'is_company': True})

    def test_10_batch_submit(self):
        b = self.Batch.create({
            'carrier_partner_id': self.partner.id,
            'period_start': '2026-01-01', 'period_end': '2026-01-31',
        })
        b.action_submit()
        self.assertEqual(b.state, 'submitted')

    def test_11_batch_approve(self):
        b = self.Batch.create({
            'carrier_partner_id': self.partner.id,
            'period_start': '2026-02-01', 'period_end': '2026-02-28',
        })
        b.action_submit()
        b.action_approve()
        self.assertEqual(b.state, 'approved')

    def test_12_approval_history(self):
        b = self.Batch.create({
            'carrier_partner_id': self.partner.id,
            'period_start': '2026-03-01', 'period_end': '2026-03-31',
        })
        b.action_submit()
        b.action_approve()
        history = self.History.search([('batch_id', '=', b.id)])
        self.assertEqual(len(history), 2)

    def test_13_batch_reject(self):
        b = self.Batch.create({
            'carrier_partner_id': self.partner.id,
            'period_start': '2026-04-01', 'period_end': '2026-04-30',
        })
        b.action_submit()
        b.action_reject()
        self.assertEqual(b.state, 'rejected')
