# -*- coding: utf-8 -*-
"""Sprint23 — DGD (Dangerous Goods Declaration) ADR Compliance tests."""
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestUnDictionary(TransactionCase):
    """UN Dictionary CRUD + validation"""

    def setUp(self):
        super().setUp()
        self.UN = self.env['tlmp.transport.un.dictionary']

    def test_create_un_entry(self):
        entry = self.UN.create({
            'un_number': 'UN1203',
            'proper_shipping_name': 'GASOLINE',
            'hazard_class': '3',
            'classification_code': 'F1',
            'packing_group': 'II',
            'tunnel_code': 'D/E',
        })
        self.assertTrue(entry)
        self.assertEqual(entry.un_number, 'UN1203')

    def test_un_number_validation(self):
        with self.assertRaises(ValidationError):
            self.UN.create({
                'un_number': '1203',
                'proper_shipping_name': 'GASOLINE',
                'hazard_class': '3',
            })

    def test_hazard_class_validation(self):
        with self.assertRaises(ValidationError):
            self.UN.create({
                'un_number': 'UN9999',
                'proper_shipping_name': 'BAD',
                'hazard_class': 'INVALID',
            })

    def test_un_number_unique(self):
        self.UN.create({
            'un_number': 'UN1203',
            'proper_shipping_name': 'GASOLINE',
            'hazard_class': '3',
        })
        with self.assertRaises(Exception):
            self.UN.create({
                'un_number': 'UN1203',
                'proper_shipping_name': 'DUPLICATE',
                'hazard_class': '3',
            })

    def test_name_get(self):
        entry = self.UN.create({
            'un_number': 'UN1203',
            'proper_shipping_name': 'GASOLINE',
            'hazard_class': '3',
        })
        name = entry.name_get()[0][1]
        self.assertIn('UN1203', name)
        self.assertIn('GASOLINE', name)


class TestDGD(TransactionCase):
    """DGD lifecycle + prefill + void"""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Test Partner'})
        self.order = self.env['tlmp.transport.order'].create({
            'transport_type': 'to_customer',
            'partner_id': self.partner.id,
            'carrier_id': self.partner.id,
        })
        self.DGD = self.env['tlmp.transport.dgd']
        self.DGDLine = self.env['tlmp.transport.dgd.line']

    def test_create_dgd(self):
        dgd = self.DGD.create({'order_id': self.order.id})
        self.assertEqual(dgd.state, 'draft')
        self.assertTrue(dgd.name)

    def test_lifecycle_draft_to_signed(self):
        dgd = self.DGD.create({'order_id': self.order.id})
        dgd.action_confirm()
        self.assertEqual(dgd.state, 'confirmed')
        self.assertTrue(dgd.confirmed_uid)
        dgd.action_generate()
        self.assertEqual(dgd.state, 'generated')
        # Need cargo lines to sign
        self.DGDLine.create({
            'dgd_id': dgd.id,
            'commodity': 'Test DG Cargo',
            'packages': 10,
            'gross_weight': 100.0,
            'net_weight': 90.0,
            'un_number': 'UN1203',
            'hazard_class': '3',
        })
        dgd.action_sign()
        self.assertEqual(dgd.state, 'signed')
        self.assertTrue(dgd.signed_uid)

    def test_dgd_validation_sign_without_lines(self):
        dgd = self.DGD.create({'order_id': self.order.id})
        dgd.action_confirm()
        dgd.action_generate()
        with self.assertRaises(UserError):
            dgd.action_sign()

    def test_void_requires_reason(self):
        dgd = self.DGD.create({'order_id': self.order.id})
        dgd.action_confirm()
        with self.assertRaises(UserError):
            dgd.action_void()
        dgd.void_reason = 'Test reason'
        dgd.action_void()
        self.assertEqual(dgd.state, 'void')

    def test_void_creates_log_entry(self):
        dgd = self.DGD.create({'order_id': self.order.id})
        dgd.void_reason = 'Customer cancelled'
        dgd.action_void()
        self.assertTrue(dgd.void_log_ids)
        self.assertEqual(dgd.void_log_ids[0].void_reason, 'Customer cancelled')

    def test_void_already_void(self):
        dgd = self.DGD.create({'order_id': self.order.id})
        dgd.void_reason = 'Test'
        dgd.action_void()
        with self.assertRaises(UserError):
            dgd.action_void()

    def test_void_recreate(self):
        """Void then create new DGD should work"""
        dgd1 = self.DGD.create({'order_id': self.order.id})
        dgd1.void_reason = 'Test void'
        dgd1.action_void()
        self.assertEqual(dgd1.state, 'void')
        dgd2 = self.DGD.create({'order_id': self.order.id})
        self.assertEqual(dgd2.state, 'draft')
        self.assertNotEqual(dgd1.id, dgd2.id)

    def test_net_weight_le_gross(self):
        dgd = self.DGD.create({'order_id': self.order.id})
        with self.assertRaises(ValidationError):
            self.DGDLine.create({
                'dgd_id': dgd.id,
                'commodity': 'Bad',
                'net_weight': 100.0,
                'gross_weight': 50.0,
            })

    def test_tunnel_code_validation(self):
        dgd = self.DGD.create({'order_id': self.order.id})
        with self.assertRaises(ValidationError):
            self.DGDLine.create({
                'dgd_id': dgd.id,
                'commodity': 'Test',
                'tunnel_code': 'X',
            })

    def test_snapshot_isolation(self):
        """Modifying cargo_line after DGD creation does not affect DGD line"""
        cargo = self.env['tlmp.transport.cargo.line'].create({
            'order_id': self.order.id,
            'description': 'Original Cargo',
            'source_type': 'manual',
            'packages': 5,
            'gross_weight': 50.0,
        })
        dgd = self.DGD.create({'order_id': self.order.id})
        dgd.action_prefill_from_cargo()
        # Modify cargo
        cargo.write({'packages': 10, 'gross_weight': 100.0})
        self.assertEqual(dgd.dgd_line_ids[0].packages, 5,
                         msg='DGD snapshot should not be affected by cargo changes')
        self.assertEqual(dgd.dgd_line_ids[0].gross_weight, 50.0,
                         msg='DGD snapshot weight should remain at original value')

    def test_state_transition_guards(self):
        dgd = self.DGD.create({'order_id': self.order.id})
        with self.assertRaises(UserError):
            dgd.action_generate()  # draft -> generate not allowed
        with self.assertRaises(UserError):
            dgd.action_sign()  # draft -> sign not allowed
        with self.assertRaises(UserError):
            dgd.action_archive()  # draft -> archive not allowed

    def test_archive_only_signed(self):
        dgd = self.DGD.create({'order_id': self.order.id})
        with self.assertRaises(UserError):
            dgd.action_archive()


class TestDangerousGoodsProfile(TransactionCase):
    """DG Profile creation and cargo_line association"""

    def setUp(self):
        super().setUp()
        self.UN = self.env['tlmp.transport.un.dictionary']
        self.Profile = self.env['tlmp.transport.dangerous.goods.profile']
        self.un_entry = self.UN.create({
            'un_number': 'UN1203',
            'proper_shipping_name': 'GASOLINE',
            'hazard_class': '3',
        })

    def test_create_profile(self):
        profile = self.Profile.create({
            'name': 'Gasoline Profile',
            'un_dictionary_id': self.un_entry.id,
        })
        self.assertEqual(profile.un_number, 'UN1203')
        self.assertEqual(profile.hazard_class, '3')

    def test_profile_unique_name(self):
        self.Profile.create({
            'name': 'Test Profile',
            'un_dictionary_id': self.un_entry.id,
        })
        with self.assertRaises(Exception):
            self.Profile.create({
                'name': 'Test Profile',
                'un_dictionary_id': self.un_entry.id,
            })
