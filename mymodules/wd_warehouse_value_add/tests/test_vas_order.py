# -*- coding: utf-8 -*-

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase
from uuid import uuid4


class TestVasOrder(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.VasOperationType = cls.env['wd.vas.operation.type']
        cls.VasOrder = cls.env['wd.vas.order']
        cls.VasOrderLine = cls.env['wd.vas.order.line']
        cls.ChargeUnit = cls.env['world.depot.charge.unit']
        cls.Warehouse = cls.env['stock.warehouse']
        cls.InboundOrder = cls.env['world.depot.inbound.order']
        cls.Project = cls.env['project.project']
        cls.Currency = cls.env['res.currency']
        cls.Operator = cls.env['res.users'].search(
            [('active', '=', True), ('share', '=', False)],
            limit=1,
        )
        cls.vas_user_group = cls.env.ref(
            'wd_warehouse_value_add.group_vas_user'
        )
        cls.env.user.write({'groups_id': [(4, cls.vas_user_group.id)]})
        cls.Operator.write({'groups_id': [(4, cls.vas_user_group.id)]})
        cls.unit = cls.ChargeUnit.create({'name': 'Hour'})
        cls.warehouse = cls.Warehouse.search([], limit=1)
        if not cls.warehouse:
            cls.warehouse = cls.Warehouse.create({
                'name': 'VAS Test Warehouse',
                'code': 'VASTEST',
            })
        cls.project = cls.Project.search([], limit=1)
        if not cls.project:
            cls.project = cls.Project.create({'name': 'VAS Test Project'})
        cls.currency = cls.Currency.search([], limit=1)
        cls.operation_type = cls.VasOperationType.create({
            'name': 'Labour',
            'code': 'LABOUR',
            'unit_id': cls.unit.id,
        })

    def _order_vals(self, **values):
        vals = {
            'order_type': 'inbound',
            'warehouse_order_billno': 'IN-001',
            'warehouse_id': self.warehouse.id,
            'operator_id': self.Operator.id,
        }
        vals.update(values)
        return vals

    def _create_inbound_order(self, state='confirm'):
        order = self.InboundOrder.create({
            'billno': 'IN-CC02-%s' % uuid4().hex[:8],
            'type': 'inbound',
            'date': '2026-09-07',
            'project': self.project.id,
            'reference': 'VAS CC-02',
            'currency_id': self.currency.id,
            'warehouse': self.warehouse.id,
            'state': state,
        })
        return order

    def _create_submittable_order(self, warehouse_order=None):
        warehouse_order = warehouse_order or self._create_inbound_order()
        order = self.VasOrder.create(self._order_vals(
            warehouse_order_billno=warehouse_order.billno,
        ))
        self.VasOrderLine.create({
            'order_id': order.id,
            'operation_type_id': self.operation_type.id,
            'quantity_time': 1,
        })
        return order, warehouse_order

    def test_model_sequence_and_draft_state(self):
        order = self.VasOrder.create(self._order_vals())
        self.assertTrue(order.name.startswith('VAS/'))
        self.assertEqual(order.state, 'draft')
        self.assertEqual(order.operator_id, self.Operator)

    def test_draft_without_lines_is_allowed(self):
        order = self.VasOrder.create(self._order_vals())
        self.assertFalse(order.line_ids)

    def test_operation_type_unit_snapshot(self):
        order = self.VasOrder.create(self._order_vals())
        line = self.VasOrderLine.create({
            'order_id': order.id,
            'operation_type_id': self.operation_type.id,
            'quantity_time': 0,
        })
        self.assertEqual(line.unit_id, self.unit)

    def test_explicit_relation_structure(self):
        fields_by_type = self.env['wd.vas.order']._fields
        self.assertEqual(
            fields_by_type['inbound_order_id'].comodel_name,
            'world.depot.inbound.order',
        )
        self.assertEqual(
            fields_by_type['outbound_order_id'].comodel_name,
            'world.depot.outbound.order',
        )
        self.assertEqual(
            fields_by_type['transfer_order_id'].comodel_name,
            'world.depot.transfer.order',
        )

    def test_relation_type_consistency(self):
        order = self.VasOrder.new(self._order_vals(
                order_type='outbound',
                inbound_order_id=1,
            ))
        with self.assertRaises(ValidationError):
            order._check_order_relation_consistency()

    def test_unique_constraints(self):
        with self.assertRaises(ValidationError):
            self.VasOperationType.create({
                'name': 'Labour Duplicate',
                'code': 'LABOUR',
                'unit_id': self.unit.id,
            })
        self.VasOrder.create(self._order_vals(name='VAS/DUPLICATE'))
        with self.assertRaises(ValidationError):
            self.VasOrder.create(self._order_vals(name='VAS/DUPLICATE'))

    def test_submit_binds_order_and_writes_audit_and_snapshots(self):
        order, warehouse_order = self._create_submittable_order()

        self.assertTrue(order.action_submit())
        self.assertEqual(order.state, 'submitted')
        self.assertEqual(order.inbound_order_id, warehouse_order)
        self.assertEqual(order.warehouse_order_billno, warehouse_order.billno)
        self.assertEqual(order.warehouse_id, warehouse_order.warehouse)
        self.assertEqual(order.submitter_id, self.env.user)
        self.assertTrue(order.submitted_at)

    def test_submit_rejects_cancelled_order_and_zero_lines(self):
        cancelled_order = self._create_inbound_order(state='cancel')
        order = self.VasOrder.create(self._order_vals(
            warehouse_order_billno=cancelled_order.billno,
        ))
        with self.assertRaises(ValidationError):
            order.action_submit()

        order, warehouse_order = self._create_submittable_order()
        order.line_ids.unlink()
        with self.assertRaises(ValidationError):
            order.action_submit()
        self.assertEqual(order.state, 'draft')
        self.assertEqual(order.inbound_order_id, self.env['world.depot.inbound.order'])

    def test_lifecycle_actions_and_locked_writes(self):
        order, _warehouse_order = self._create_submittable_order()
        order.action_submit()
        with self.assertRaises(ValidationError):
            order.write({'notes': 'not allowed'})

        order.action_unsubmit()
        self.assertEqual(order.state, 'draft')
        self.assertEqual(order.unsubmitted_by, self.env.user)
        order.action_cancel('No longer needed')
        self.assertEqual(order.state, 'cancelled')
        with self.assertRaises(ValidationError):
            order.action_unsubmit()

    def test_draft_cancel_requires_reason(self):
        order = self.VasOrder.create(self._order_vals())
        with self.assertRaises(ValidationError):
            order.action_cancel()
        order.action_cancel('Duplicate draft')
        self.assertEqual(order.state, 'cancelled')
