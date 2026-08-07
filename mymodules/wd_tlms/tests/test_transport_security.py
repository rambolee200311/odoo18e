# -*- coding: utf-8 -*-
"""权限隔离测试 — 非 admin 不可删 event、不可改 cargo_line"""
from odoo.tests.common import TransactionCase
from odoo.exceptions import AccessError


class TestTransportSecurity(TransactionCase):
    """Security: access control for event/cargo"""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Test'})
        self.order = self.env['tlmp.transport.order'].create({
            'transport_type': 'to_customer', 'partner_id': self.partner.id,
            'carrier_id': self.partner.id,
        })
        # Create operator user
        self.op_user = self.env['res.users'].create({
            'name': 'Operator', 'login': 'test_op',
            'groups_id': [(4, self.env.ref('wd_tlms.group_tlm_operator').id)],
        })

    def test_60_event_unlink_denied(self):
        evt = self.env['tlmp.transport.event'].create({
            'order_id': self.order.id,
            'event_type_id': self.env.ref('wd_tlms.evt_pickup_arrived').id,
        })
        with self.assertRaises(AccessError):
            evt.sudo(self.op_user).unlink()

    def test_61_cargo_modify_denied(self):
        line = self.env['tlmp.transport.cargo.line'].create({
            'order_id': self.order.id, 'description': 'Test',
        })
        with self.assertRaises(AccessError):
            line.sudo(self.op_user).write({'description': 'Hacked'})

    def test_62_operator_create_event_ok(self):
        evt = self.env['tlmp.transport.event'].sudo(self.op_user).create({
            'order_id': self.order.id,
            'event_type_id': self.env.ref('wd_tlms.evt_pickup_arrived').id,
        })
        self.assertTrue(evt.id)
