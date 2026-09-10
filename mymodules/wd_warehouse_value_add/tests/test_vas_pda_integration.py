# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase


class TestVasPdaIntegration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.write({
            'groups_id': [(4, cls.env.ref(
                'wd_warehouse_value_add.group_vas_manager'
            ).id)],
        })
        cls.operator = cls.env['res.users'].search(
            [('active', '=', True), ('share', '=', False)],
            limit=1,
        )
        cls.operator.write({
            'groups_id': [(4, cls.env.ref(
                'wd_warehouse_value_add.group_vas_user'
            ).id)],
        })
        cls.warehouse = cls.env['stock.warehouse'].search([], limit=1)
        cls.unit = cls.env['world.depot.charge.unit'].create({'name': 'PDA Piece'})
        cls.operation = cls.env['wd.vas.operation.type'].create({
            'name': 'PDA Label',
            'code': 'PDA-LABEL',
            'unit_id': cls.unit.id,
        })
        cls.project = cls.env['project.project'].create({
            'name': 'PDA Project',
            'owner': cls.env['res.partner'].create({'name': 'PDA Customer'}).id,
        })

    def test_valid_submit_persists_binding_and_snapshot(self):
        warehouse_order = self.env['world.depot.inbound.order'].create({
            'type': 'inbound',
            'date': '2026-09-07',
            'project': self.project.id,
            'reference': 'PDA-CC04',
            'warehouse': self.warehouse.id,
        })
        order = self.env['wd.vas.order'].create({
            'order_type': 'inbound',
            'warehouse_order_billno': warehouse_order.billno,
            'warehouse_id': self.warehouse.id,
            'operator_id': self.operator.id,
        })
        self.env['wd.vas.order.line'].create({
            'order_id': order.id,
            'operation_type_id': self.operation.id,
            'quantity_time': 1,
        })

        order.action_submit()

        self.assertEqual(order.state, 'submitted')
        self.assertEqual(order.inbound_order_id, warehouse_order)
        self.assertEqual(order.warehouse_order_billno, warehouse_order.billno)
        self.assertEqual(order.warehouse_id, warehouse_order.warehouse)
        self.assertEqual(order.submitter_id, self.env.user)
        self.assertTrue(order.submitted_at)

    def test_unassociated_draft_can_submit_after_order_binding(self):
        warehouse_order = self.env['world.depot.inbound.order'].create({
            'type': 'inbound',
            'date': '2026-09-07',
            'project': self.project.id,
            'reference': 'PDA-CC04-DRAFT',
            'warehouse': self.warehouse.id,
        })
        order = self.env['wd.vas.order'].create({
            'order_type': 'inbound',
            'operator_id': self.operator.id,
        })
        self.env['wd.vas.order.line'].create({
            'order_id': order.id,
            'operation_type_id': self.operation.id,
            'quantity_time': 1,
        })

        self.assertEqual(order.state, 'draft')
        self.assertFalse(order.warehouse_order_billno)
        self.assertFalse(order.warehouse_id)

        order.write({
            'warehouse_order_billno': warehouse_order.billno,
        })
        order.action_submit()

        self.assertEqual(order.state, 'submitted')
        self.assertEqual(order.inbound_order_id, warehouse_order)
        self.assertEqual(order.warehouse_order_billno, warehouse_order.billno)
        self.assertEqual(order.warehouse_id, warehouse_order.warehouse)
