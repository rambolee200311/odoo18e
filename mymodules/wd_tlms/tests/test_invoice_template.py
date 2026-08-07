from odoo.tests.common import TransactionCase

class TestInvoiceTemplate(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Template = self.env['tlmp.carrier.invoice.template']
        self.partner = self.env['res.partner'].create({'name': 'Test Carrier', 'is_company': True})
        self.profile = self.env['tlmp.carrier.profile'].create({
            'partner_id': self.partner.id,
            'carrier_code': 'TEST', 'carrier_type': 'truck_fuel',
        })

    def test_01_create_template(self):
        t = self.Template.create({
            'name': 'DHL Standard',
            'carrier_profile_id': self.profile.id,
            'file_type': 'csv',
            'mapping_json': '{"A":"tracking_number","F":"amount"}',
        })
        self.assertTrue(t.id)
        self.assertTrue(t.is_active)
