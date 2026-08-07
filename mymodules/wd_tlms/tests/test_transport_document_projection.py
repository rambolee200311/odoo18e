# -*- coding: utf-8 -*-
"""Sprint48-B: Cargo Summary projection + order cargo snapshot freeze."""
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestDocumentProjection(TransactionCase):
    """Quote Cargo Summary and Order cargo snapshot behaviour."""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create(
            {'name': 'Test Customer'})
        self.carrier = self.env['res.partner'].create({
            'name': 'Test Carrier', 'is_carrier': True})
        self.request = self.env['tlmp.transport.request'].create({
            'request_type': 'commercial',
            'destination_type': 'customer',
            'destination_street': 'Test Street',
            'partner_id': self.partner.id,
            'cargo_type': 'container',
            'cargo_description': '50 pallets Vitamin C',
            'cargo_weight': 12000.0,
            'cargo_volume': 40.0,
        })
        self.inquiry = self.env['tlmp.transport.inquiry'].create({
            'request_id': self.request.id,
            'partner_id': self.carrier.id,
            'cargo_summary': '50 pallets Vitamin C',
        })
        self.inquiry.write({'state': 'accepted'})
        self.quote = self.env['tlmp.transport.quote'].browse(
            self.inquiry.action_create_quote()['res_id'])

    def test_01_quote_cargo_summary(self):
        self.assertEqual(self.quote.cargo_source_reference, self.request.name)
        self.assertEqual(self.quote.cargo_summary, '50 pallets Vitamin C')
        self.assertEqual(self.quote.cargo_weight_kg, 12000.0)
        self.assertEqual(self.quote.cargo_volume_m3, 40.0)

    def test_02_order_snapshot_created_and_frozen(self):
        self.quote.action_send()
        self.quote.action_accept()
        order = self.quote.transport_order_id
        self.assertTrue(order)
        self.assertEqual(order.cargo_snapshot_version, 1)
        self.assertEqual(order.snapshot_status, 'draft')
        order.action_confirm()
        self.assertEqual(order.snapshot_status, 'confirmed')
        with self.assertRaises(UserError):
            order.write({'cargo_weight': 9999.0})
        self.assertEqual(order.cargo_weight, 12000.0)

    def test_03_order_cargo_lines_copied(self):
        self.env['tlmp.transport.cargo.line'].create({
            'request_id': self.request.id, 'description': 'PAL001',
            'packaging_level': 'handling_unit', 'qty': 10.0,
            'pallet_gross_weight_kg': 30.0, 'pallet_volume_m3': 2.0,
        })
        self.request._onchange_cargo_line_totals()
        self.quote.action_send()
        self.quote.action_accept()
        order = self.quote.transport_order_id
        self.assertEqual(len(order.cargo_line_ids), 1)
        self.assertEqual(order.cargo_line_ids.packaging_level, 'handling_unit')
