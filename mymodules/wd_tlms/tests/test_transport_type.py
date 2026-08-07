# -*- coding: utf-8 -*-
"""Sprint24 — Transport Type Master Data + Carrier Service tests."""
from odoo.tests.common import TransactionCase


class TestTransportType(TransactionCase):
    """Transport Type CRUD + field tests"""

    def setUp(self):
        super().setUp()
        self.TT = self.env['tlmp.transport.type']

    def test_create_type(self):
        t = self.TT.create({
            'code': 'test_ftl', 'name': 'Test FTL',
            'category': 'ftl', 'mode': 'road',
        })
        self.assertTrue(t)
        self.assertEqual(t.code, 'test_ftl')
        self.assertEqual(t.category, 'ftl')

    def test_code_unique(self):
        self.TT.create({
            'code': 'unique_code', 'name': 'First',
            'category': 'ftl', 'mode': 'road',
        })
        with self.assertRaises(Exception):
            self.TT.create({
                'code': 'unique_code', 'name': 'Duplicate',
                'category': 'ftl', 'mode': 'road',
            })

    def test_category_mode_selection(self):
        for cat, _ in self.TT._fields['category'].selection:
            t = self.TT.create({
                'code': 'cat_%s' % cat, 'name': cat,
                'category': cat, 'mode': 'road',
            })
            self.assertEqual(t.category, cat)
        for mode, _ in self.TT._fields['mode'].selection:
            t = self.TT.create({
                'code': 'mode_%s' % mode, 'name': mode,
                'category': 'ftl', 'mode': mode,
            })
            self.assertEqual(t.mode, mode)

    def test_name_get(self):
        t = self.TT.create({
            'code': 'ng', 'name': 'Test',
            'category': 'ftl', 'mode': 'road',
        })
        name = t.name_get()[0][1]
        self.assertIn('Test', name)
        self.assertIn('ng', name)

    def test_get_by_code(self):
        self.TT.create({
            'code': 'lookup_test', 'name': 'Lookup',
            'category': 'ftl', 'mode': 'road',
        })
        t = self.TT._get_by_code('lookup_test')
        self.assertTrue(t)
        self.assertEqual(t.name, 'Lookup')

    def test_type_map(self):
        self.TT.create({
            'code': 'tm1', 'name': 'TM1',
            'category': 'ftl', 'mode': 'road',
        })
        tmap = self.TT._type_map()
        self.assertIn('tm1', tmap)
        self.assertIsInstance(tmap['tm1'], int)

    def test_is_active(self):
        t = self.TT.create({
            'code': 'active_test', 'name': 'Active Test',
            'category': 'ftl', 'mode': 'road', 'is_active': False,
        })
        self.assertFalse(t.is_active)


class TestCarrierService(TransactionCase):
    """Carrier Service CRUD tests"""

    def setUp(self):
        super().setUp()
        self.CS = self.env['tlmp.carrier.service']

    def test_create_service(self):
        s = self.CS.create({
            'code': 'test_parcel', 'name': 'Test Parcel',
            'service_type': 'parcel',
        })
        self.assertTrue(s)
        self.assertEqual(s.code, 'test_parcel')

    def test_code_unique(self):
        self.CS.create({
            'code': 'svc_unique', 'name': 'First',
            'service_type': 'parcel',
        })
        with self.assertRaises(Exception):
            self.CS.create({
                'code': 'svc_unique', 'name': 'Duplicate',
                'service_type': 'parcel',
            })

    def test_service_type(self):
        for st, _ in self.CS._fields['service_type'].selection:
            s = self.CS.create({
                'code': 'st_%s' % st, 'name': st,
                'service_type': st,
            })
            self.assertEqual(s.service_type, st)

    def test_carrier_association(self):
        partner = self.env['res.partner'].create({
            'name': 'Test Carrier', 'is_company': True,
        })
        s = self.CS.create({
            'code': 'with_carrier', 'name': 'With Carrier',
            'service_type': 'express',
            'carrier_id': partner.id,
        })
        self.assertEqual(s.carrier_id.id, partner.id)
        self.assertEqual(s.carrier_id.name, 'Test Carrier')
