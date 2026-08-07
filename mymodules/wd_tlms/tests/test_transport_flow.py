# -*- coding: utf-8 -*-
"""端到端业务链 + 附件聚合 + tracking_state 测试"""
from odoo.tests.common import TransactionCase
from odoo import fields


class TestTransportFlow(TransactionCase):
    """Terminal→Warehouse / Empty Depot / Warehouse→Customer"""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Test'})
        self.sender = self.env['res.partner'].create({
            'name': 'Terminal', 'street': 'Port 1', 'city': 'Rotterdam',
        })
        self.scene = self.env['tlmp.transport.scene'].create({
            'name': 'Terminal→Warehouse', 'code': 'terminal_to_warehouse',
            'scene_type': 'plan_driven',
        })
        self.empty_scene = self.env['tlmp.transport.scene'].create({
            'name': 'Empty Depot', 'code': 'empty_depot',
            'scene_type': 'plan_driven',
        })
        self.evt_pickup = self.env['tlmp.transport.event.type'].create({
            'name': 'Pickup', 'code': 'PICKUP_ARRIVED',
            'is_base_event': True, 'sequence_order': 10,
        })
        self.evt_delivery = self.env['tlmp.transport.event.type'].create({
            'name': 'Delivery', 'code': 'DELIVERY_COMPLETED',
            'is_base_event': True, 'sequence_order': 20,
        })

    def test_70_terminal_warehouse_flow(self):
        """Terminal→Warehouse: order → cargo → events → CMR"""
        order = self.env['tlmp.transport.order'].create({
            'transport_type': 'port_to_warehouse', 'partner_id': self.partner.id,
            'carrier_id': self.partner.id, 'scene_id': self.scene.id,
        })
        self.env['tlmp.transport.cargo.line'].create({
            'order_id': order.id, 'description': 'Container goods',
            'qty': 20.0, 'gross_weight': 1000.0,
        })
        self.env['tlmp.transport.event'].create({
            'order_id': order.id, 'event_type_id': self.evt_pickup.id,
        })
        cmr = self.env['tlmp.cmr'].create_cmr_with_cargo(order)
        self.assertTrue(cmr.id)
        self.assertTrue(len(cmr.line_ids) > 0)

    def test_71_empty_depot_flow(self):
        """empty_depot: order(container only) → events → CMR(no cargo)"""
        order = self.env['tlmp.transport.order'].create({
            'transport_type': 'warehouse_transfer', 'partner_id': self.partner.id,
            'carrier_id': self.partner.id, 'scene_id': self.empty_scene.id,
            'container_no_set': 'CONTAINER-001',
        })
        self.env['tlmp.transport.event'].create({
            'order_id': order.id, 'event_type_id': self.evt_pickup.id,
        })
        cmr = self.env['tlmp.cmr'].create_cmr_with_cargo(order)
        self.assertTrue(cmr.id)
        self.assertFalse(cmr.line_ids, msg='Empty depot CMR should have no cargo lines')

    def test_72_warehouse_customer_flow(self):
        """Warehouse→Customer: order(outbound cargo) → events → CMR"""
        order = self.env['tlmp.transport.order'].create({
            'transport_type': 'to_customer', 'partner_id': self.partner.id,
            'carrier_id': self.partner.id, 'pickup_location_id': self.sender.id,
        })
        self.env['tlmp.transport.cargo.line'].create({
            'order_id': order.id, 'description': 'Outbound goods',
            'qty': 15.0, 'source_type': 'outbound_order',
        })
        cmr = self.env['tlmp.cmr'].create_cmr_with_cargo(order)
        self.assertTrue(cmr.id)

    def test_80_attachment_aggregation(self):
        """computed attachment fields aggregate correctly"""
        order = self.env['tlmp.transport.order'].create({
            'transport_type': 'to_customer', 'partner_id': self.partner.id,
            'carrier_id': self.partner.id,
        })
        # No attachments should mean empty computed fields
        self.assertFalse(order.cmr_attachment_ids)
        self.assertFalse(order.event_attachment_ids)
        self.assertFalse(order.exception_attachment_ids)
        self.assertFalse(order.charge_attachment_ids)

    def test_81_tracking_state_flow(self):
        """tracking_state: draft→pending→in_transit→completed + exception_hold"""
        order = self.env['tlmp.transport.order'].create({
            'transport_type': 'to_customer', 'partner_id': self.partner.id,
            'carrier_id': self.partner.id,
        })
        self.assertEqual(order.tracking_state, 'draft')
        order.write({'tracking_state': 'pending_pickup'})
        self.assertEqual(order.tracking_state, 'pending_pickup')
        order.write({'tracking_state': 'in_transit'})
        self.assertEqual(order.tracking_state, 'in_transit')
        order.write({'tracking_state': 'completed'})
        self.assertEqual(order.tracking_state, 'completed')
        order.write({'tracking_state': 'exception_hold'})
        self.assertEqual(order.tracking_state, 'exception_hold')
