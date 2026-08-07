from odoo.tests.common import TransactionCase

class TestCarrierProfile(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Profile = self.env['tlmp.carrier.profile']
        self.partner = self.env['res.partner'].create({'name': 'Test Carrier', 'is_company': True})

    def test_01_create_profile(self):
        p = self.Profile.create({
            'partner_id': self.partner.id,
            'carrier_code': 'TEST01',
            'carrier_type': 'truck_fuel',
        })
        self.assertTrue(p.id)
        self.assertEqual(p.carrier_code, 'TEST01')

    def test_02_unique_carrier_code(self):
        self.Profile.create({'partner_id': self.partner.id, 'carrier_code': 'UNIQUE', 'carrier_type': 'truck_fuel'})
        p2 = self.env['res.partner'].create({'name': 'Other', 'is_company': True})
        with self.assertRaises(Exception):
            self.Profile.create({'partner_id': p2.id, 'carrier_code': 'UNIQUE', 'carrier_type': 'truck_fuel'})

    def test_03_get_or_create_existing(self):
        p = self.Profile._get_or_create(self.partner)
        self.assertFalse(p)
        p1 = self.Profile.create({'partner_id': self.partner.id, 'carrier_code': 'EXIST', 'carrier_type': 'truck_fuel'})
        p2 = self.Profile._get_or_create(self.partner)
        self.assertEqual(p1.id, p2.id)
