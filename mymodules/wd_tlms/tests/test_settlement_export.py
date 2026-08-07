from odoo.tests.common import TransactionCase

class TestSettlementExport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Wizard = self.env['tlmp.settlement.export.wizard']

    def test_20_wizard_create(self):
        w = self.Wizard.create({
            'period_start': '2026-01-01',
            'period_end': '2026-12-31',
        })
        self.assertTrue(w.id)
        self.assertEqual(w.period_start, fields.Date.to_date('2026-01-01'))
