# -*- coding: utf-8 -*-
"""Product ADR + MRN/T1 — 字段 CRUD 测试"""
from odoo.tests.common import TransactionCase


class TestProductADR(TransactionCase):
    """product.product ADR fields + order MRN/T1 fields"""

    def setUp(self):
        super().setUp()
        self.product = self.env['product.product'].create({
            'name': 'Test DG Product',
            'is_dangerous_good': True,
            'adr_un_number': 'UN1203',
            'adr_class': '3',
            'adr_packing_group': 'II',
        })
        self.partner = self.env['res.partner'].create({'name': 'Test'})
        self.order = self.env['tlmp.transport.order'].create({
            'transport_type': 'to_customer', 'partner_id': self.partner.id,
            'carrier_id': self.partner.id,
            'mrn_code': 'MRN-2026-00001',
            't1_ref': 'T1-001',
            'dg_file_ref': 'DG-FILE-001',
            'adr_quantity': 10.0,
            'adr_weight': 500.0,
        })

    def test_50_product_adr_fields(self):
        self.assertTrue(self.product.is_dangerous_good)
        self.assertEqual(self.product.adr_un_number, 'UN1203')
        self.assertEqual(self.product.adr_class, '3')
        self.assertEqual(self.product.adr_packing_group, 'II')

    def test_51_order_mrn_t1(self):
        self.assertEqual(self.order.mrn_code, 'MRN-2026-00001')
        self.assertEqual(self.order.t1_ref, 'T1-001')

    def test_52_order_dg_file(self):
        self.assertEqual(self.order.dg_file_ref, 'DG-FILE-001')
        self.assertEqual(self.order.adr_quantity, 10.0)
        self.assertEqual(self.order.adr_weight, 500.0)
