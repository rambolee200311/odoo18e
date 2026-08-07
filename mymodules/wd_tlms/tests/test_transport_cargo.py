# -*- coding: utf-8 -*-
"""Cargo Line + CMR Cargo Sync — 数据隔离 + 快照冻结测试"""
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestCargoLine(TransactionCase):
    """CargoLine: CRUD, owner exclusive, copy isolation, source"""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Test'})
        self.order = self.env['tlmp.transport.order'].create({
            'transport_type': 'to_customer', 'partner_id': self.partner.id,
            'carrier_id': self.partner.id,
        })
        self.request = self.env['tlmp.transport.request'].create({
            'request_type': 'plan_driven', 'destination_type': 'warehouse',
            'cargo_type': 'pallet',
        })

    def test_30_cargo_create(self):
        line = self.env['tlmp.transport.cargo.line'].create({
            'order_id': self.order.id, 'description': 'Widgets',
            'qty': 10.0, 'packages': 2,
        })
        self.assertTrue(line.id)
        self.assertEqual(line.qty, 10.0)
        self.assertEqual(line.packages, 2)

    def test_31_cargo_owner_exclusive(self):
        with self.assertRaises(ValidationError):
            self.env['tlmp.transport.cargo.line'].create({
                'request_id': self.request.id, 'order_id': self.order.id,
                'description': 'Bad',
            })

    def test_32_cargo_request_to_order(self):
        cl = self.env['tlmp.transport.cargo.line'].create({
            'request_id': self.request.id, 'description': 'Test Cargo',
            'qty': 5.0,
        })
        copy = cl.copy_to_order(self.order)
        self.assertTrue(copy.id)
        self.assertEqual(copy.description, 'Test Cargo')
        self.assertEqual(copy.qty, 5.0)
        self.assertEqual(copy.order_id.id, self.order.id)
        self.assertFalse(copy.request_id)

    def test_33_cargo_copy_isolation(self):
        cl = self.env['tlmp.transport.cargo.line'].create({
            'request_id': self.request.id, 'description': 'Original',
            'gross_weight': 100.0,
        })
        copy = cl.copy_to_order(self.order)
        copy.write({'gross_weight': 120.0})
        self.assertEqual(cl.gross_weight, 100.0, msg='Request cargo unchanged')
        self.assertEqual(copy.gross_weight, 120.0, msg='Order cargo updated')

    def test_34_cargo_source_type(self):
        line = self.env['tlmp.transport.cargo.line'].create({
            'order_id': self.order.id, 'description': 'Manual',
            'source_type': 'manual',
        })
        self.assertEqual(line.source_type, 'manual')
        line2 = self.env['tlmp.transport.cargo.line'].create({
            'order_id': self.order.id, 'description': 'System',
            'source_type': 'system',
        })
        self.assertEqual(line2.source_type, 'system')


class TestCMRCargoSync(TransactionCase):
    """CMR create with cargo, source trace, anti-duplicate, snapshot"""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Test'})
        self.sender = self.env['res.partner'].create({
            'name': 'Sender', 'street': 'Street 1', 'city': 'City',
        })
        self.order = self.env['tlmp.transport.order'].create({
            'transport_type': 'to_customer', 'partner_id': self.partner.id,
            'carrier_id': self.partner.id, 'pickup_location_id': self.sender.id,
        })

    def test_40_cmr_create_with_cargo(self):
        self.env['tlmp.transport.cargo.line'].create({
            'order_id': self.order.id, 'description': 'Widgets',
            'qty': 10.0, 'gross_weight': 200.0,
        })
        cmr = self.env['tlmp.cmr'].create_cmr_with_cargo(self.order)
        self.assertTrue(cmr.id)
        self.assertTrue(cmr.line_ids, msg='CMR should have cargo lines')
        self.assertEqual(len(cmr.line_ids), 1)
        self.assertEqual(cmr.line_ids[0].qty, 10.0)

    def test_41_cmr_source_trace(self):
        cl = self.env['tlmp.transport.cargo.line'].create({
            'order_id': self.order.id, 'description': 'Traceable', 'qty': 5.0,
        })
        cmr = self.env['tlmp.cmr'].create_cmr_with_cargo(self.order)
        self.assertEqual(cmr.line_ids[0].source_cargo_line_id.id, cl.id)

    def test_42_cmr_anti_duplicate(self):
        self.env['tlmp.transport.cargo.line'].create({
            'order_id': self.order.id, 'description': 'Dup', 'qty': 3.0,
        })
        cmr1 = self.env['tlmp.cmr'].create_cmr_with_cargo(self.order)
        cmr2 = self.env['tlmp.cmr'].create_cmr_with_cargo(self.order)
        self.assertEqual(cmr1.id, cmr2.id, msg='Should return existing CMR')

    def test_43_cmr_snapshot_freeze(self):
        cl = self.env['tlmp.transport.cargo.line'].create({
            'order_id': self.order.id, 'description': 'Snapshot', 'gross_weight': 100.0,
        })
        cmr = self.env['tlmp.cmr'].create_cmr_with_cargo(self.order)
        cl.write({'gross_weight': 200.0})
        self.assertEqual(cmr.line_ids[0].gross_weight, 100.0, msg='CMR snapshot unchanged')

    def test_44_cmr_empty_cargo(self):
        cmr = self.env['tlmp.cmr'].create_cmr_with_cargo(self.order)
        self.assertTrue(cmr.id, msg='Empty CMR created')
        self.assertFalse(cmr.line_ids, msg='No cargo lines')

    def test_45_cmr_legacy_cargo(self):
        self.order.write({'cargo_description': 'Old cargo', 'cargo_weight': 500.0})
        cmr = self.env['tlmp.cmr'].create_cmr_with_cargo(self.order)
        self.assertTrue(cmr.id)
