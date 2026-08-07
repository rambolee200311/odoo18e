# -*- coding: utf-8 -*-
"""Sprint48-C regression: three business scenarios on the new Cargo Node model."""
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestBusinessScenarios(TransactionCase):
    """一柜20托 / 托盘拆件双订单 / 报价快照冻结隔离."""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create(
            {'name': 'Scenario Customer'})
        self.carrier = self.env['res.partner'].create({
            'name': 'Scenario Carrier', 'is_carrier': True})
        self.request = self.env['tlmp.transport.request'].create({
            'request_type': 'commercial',
            'destination_type': 'customer',
            'destination_street': 'Test Street',
            'partner_id': self.partner.id,
            'cargo_type': 'container',
        })
        self.Cargo = self.env['tlmp.transport.cargo.line']

    def _create_quote_order(self):
        inquiry = self.env['tlmp.transport.inquiry'].create({
            'request_id': self.request.id,
            'partner_id': self.carrier.id,
        })
        inquiry.write({'state': 'accepted'})
        quote = self.env['tlmp.transport.quote'].browse(
            inquiry.action_create_quote()['res_id'])
        quote.action_send()
        quote.action_accept()
        return quote.transport_order_id

    def test_01_container_20_pallets(self):
        container = self.Cargo.create({
            'request_id': self.request.id, 'description': 'C001',
            'packaging_level': 'container', 'node_type': 'equipment',
        })
        for i in range(20):
            self.Cargo.create({
                'request_id': self.request.id,
                'parent_cargo_line_id': container.id,
                'description': 'PAL%02d' % (i + 1),
                'packaging_level': 'handling_unit',
                'qty': 1.0, 'pieces_per_pallet': 10,
                'pallet_gross_weight_kg': 30.0,
                'pallet_volume_m3': 1.5,
            })
        self.request._onchange_cargo_line_totals()
        self.assertEqual(self.request.pallet_count, 20)
        self.assertEqual(self.request.package_count, 200)
        self.assertEqual(self.request.cargo_weight, 600.0)
        self.assertEqual(self.request.cargo_volume, 30.0)
        self.assertEqual(container.pallets_in_container, 20)

    def test_02_pallet_split_two_orders(self):
        self.Cargo.create({
            'request_id': self.request.id, 'description': 'PAL001',
            'packaging_level': 'handling_unit', 'qty': 10.0,
            'pieces_per_pallet': 20, 'pallet_gross_weight_kg': 30.0,
            'pallet_volume_m3': 2.0,
        })
        self.request._onchange_cargo_line_totals()
        order1 = self._create_quote_order()
        # Second order from the same request/cargo node (direct inquiry path).
        inquiry2 = self.env['tlmp.transport.inquiry'].create({
            'request_id': self.request.id,
            'partner_id': self.carrier.id,
        })
        inquiry2.write({'state': 'accepted'})
        quote2 = self.env['tlmp.transport.quote'].browse(
            inquiry2.action_create_quote()['res_id'])
        quote2.action_send()
        quote2.action_accept()
        order2 = quote2.transport_order_id
        self.assertNotEqual(order1.id, order2.id)
        self.assertEqual(order1.request_id.id, self.request.id)
        self.assertEqual(order2.request_id.id, self.request.id)
        self.assertEqual(len(order1.cargo_line_ids), 1)
        self.assertEqual(len(order2.cargo_line_ids), 1)
        self.assertEqual(order1.cargo_line_ids.description, 'PAL001')
        self.assertEqual(order2.cargo_line_ids.description, 'PAL001')

    def test_03_quote_snapshot_freeze_isolation(self):
        pallet = self.Cargo.create({
            'request_id': self.request.id, 'description': 'PAL001',
            'packaging_level': 'handling_unit', 'qty': 10.0,
            'pieces_per_pallet': 20, 'pallet_gross_weight_kg': 30.0,
            'pallet_volume_m3': 2.0,
        })
        self.request._onchange_cargo_line_totals()
        order = self._create_quote_order()
        self.assertEqual(order.cargo_weight, 300.0)
        order.action_confirm()
        self.assertEqual(order.snapshot_status, 'confirmed')
        pallet.write({'pallet_gross_weight_kg': 99.0})
        self.request._onchange_cargo_line_totals()
        self.assertEqual(order.cargo_weight, 300.0,
                         'Order snapshot must not change after confirm')
        with self.assertRaises(UserError):
            order.write({'cargo_weight': 999.0})
