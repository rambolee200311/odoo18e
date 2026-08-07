# -*- coding: utf-8 -*-
"""Sprint46: Request→Plan→Order address snapshot chain tests"""
from odoo.tests.common import TransactionCase


class TestSnapshotChain(TransactionCase):
    def setUp(self):
        super().setUp()
        self.wh1 = self.env['stock.warehouse'].create({'name': 'WH1', 'code': 'WH1'})
        self.terminal = self.env['res.partner'].create({
            'name': 'Rotterdam Terminal', 'street': 'Boompijes 258',
            'zip': '3011XZ', 'city': 'Rotterdam',
        })
        self.customer = self.env['res.partner'].create({
            'name': 'Test Customer', 'street': 'Main St 1', 'city': 'Amsterdam',
        })
        self.carrier = self.env['res.partner'].create({
            'name': 'Test Carrier', 'is_carrier': True,
        })
        self.scene_tw = self.env['tlmp.transport.scene'].search(
            [('code', '=', 'terminal_to_warehouse')], limit=1)

    def _mk_request(self):
        req = self.env['tlmp.transport.request'].create({
            'request_type': 'plan_driven',
            'destination_type': 'warehouse',
            'cargo_type': 'container',
            'scene_id': self.scene_tw.id,
            'terminal_id': self.terminal.id,
            'warehouse_id': self.wh1.id,
            'origin_street': self.terminal.street,
            'origin_city': self.terminal.city,
            'destination_street': 'Warehouse St 1',
            'destination_city': 'Rotterdam',
        })
        # Container line required for plan -> order creation
        self.env['tlmp.transport.cargo.line'].create({
            'request_id': req.id,
            'description': 'Test Container',
            'container_no': 'TEST1234567',
            'container_type': '20GP',
        })
        return req

    def test_go_schedule_plan_snapshot_matches_request(self):
        """transport_request.action_go_schedule() 后 plan 地址快照与 request 一致"""
        req = self._mk_request()
        req.action_go_schedule()
        plan = self.env['pickup.plan'].search(
            [('transport_request_id', '=', req.id)], limit=1)
        self.assertTrue(plan, 'Pickup Plan should be created')
        self.assertEqual(plan.origin_street, req.origin_street)
        self.assertEqual(plan.origin_city, req.origin_city)
        self.assertEqual(plan.destination_street, req.destination_street)
        self.assertEqual(plan.destination_city, req.destination_city)

    def test_create_order_from_plan_address_matches(self):
        """pickup.plan.action_create_transport_order() 后 order 地址与 plan 一致"""
        req = self._mk_request()
        req.action_go_schedule()
        plan = self.env['pickup.plan'].search(
            [('transport_request_id', '=', req.id)], limit=1)
        plan.carrier_id = self.carrier.id
        plan.action_create_transport_order()
        order = self.env['tlmp.transport.order'].search(
            [('pickup_plan_id', '=', plan.id)], limit=1)
        self.assertTrue(order, 'Order should be created')
        self.assertEqual(order.origin_street, plan.origin_street)
        self.assertEqual(order.origin_city, plan.origin_city)
        self.assertEqual(order.destination_street, plan.destination_street)
        self.assertEqual(order.destination_city, plan.destination_city)

    def test_order_address_readonly_after_confirm(self):
        """Order 确认后地址字段只读（后续改动被 ORM 阻止或快照保持）"""
        req = self._mk_request()
        req.action_go_schedule()
        plan = self.env['pickup.plan'].search(
            [('transport_request_id', '=', req.id)], limit=1)
        plan.carrier_id = self.carrier.id
        plan.action_create_transport_order()
        order = self.env['tlmp.transport.order'].search(
            [('pickup_plan_id', '=', plan.id)], limit=1)
        order.action_confirm()
        # 确认后写入地址应保持原值（readonly 字段被 ORM 忽略或阻止）
        try:
            order.write({'destination_city': 'Changed City'})
        except Exception:
            pass
        self.assertEqual(order.destination_city, 'Rotterdam')
