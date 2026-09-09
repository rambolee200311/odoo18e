# -*- coding: utf-8 -*-

from uuid import uuid4

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestVasSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.VasOrder = cls.env['wd.vas.order']
        cls.Warehouse = cls.env['stock.warehouse']
        cls.warehouse = cls.Warehouse.search([], limit=1)
        users = cls.env['res.users'].search([
            ('active', '=', True),
            ('share', '=', False),
            ('id', '!=', cls.env.user.id),
        ], limit=3)
        if len(users) < 3:
            raise AssertionError('At least three active test users are required.')
        cls.vas_user, cls.manager, cls.unauthorized = users
        cls.user_group = cls.env.ref('wd_warehouse_value_add.group_vas_user')
        cls.manager_group = cls.env.ref(
            'wd_warehouse_value_add.group_vas_manager'
        )
        unit = cls.env['world.depot.charge.unit'].create({
            'name': 'Security Test Unit',
        })
        cls.operation_type = cls.env['wd.vas.operation.type'].create({
            'name': 'Security Test Operation',
            'code': 'SEC-%s' % uuid4().hex[:8],
            'unit_id': unit.id,
        })
        for user in users:
            user.write({
                'groups_id': [
                    (3, cls.user_group.id),
                    (3, cls.manager_group.id),
                ],
            })
        cls.vas_user.write({'groups_id': [(4, cls.user_group.id)]})
        cls.manager.write({'groups_id': [(4, cls.manager_group.id)]})

    def _order_vals(self):
        return {
            'order_type': 'inbound',
            'warehouse_order_billno': 'SEC-%s' % uuid4().hex[:8],
            'warehouse_id': self.warehouse.id,
            'operator_id': self.vas_user.id,
        }

    def test_acl_and_record_rules_split_user_and_manager_visibility(self):
        user_order = self.VasOrder.with_user(self.vas_user).create(
            self._order_vals()
        )
        manager_order = self.VasOrder.with_user(self.manager).create(
            self._order_vals()
        )

        self.assertEqual(
            self.VasOrder.with_user(self.vas_user).search([]),
            user_order,
        )
        self.assertIn(
            manager_order,
            self.VasOrder.with_user(self.manager).search([]),
        )
        with self.assertRaises(AccessError):
            self.VasOrder.with_user(self.unauthorized).search([])

    def test_action_permission_is_checked_server_side(self):
        order = self.VasOrder.with_user(self.vas_user).create(
            self._order_vals()
        )
        with self.assertRaises(AccessError):
            order.with_user(self.unauthorized).action_cancel(
                'Unauthorized attempt'
            )

    def test_operation_type_is_manager_configured_and_user_read_only(self):
        operation_type = self.operation_type
        self.assertTrue(
            operation_type.with_user(self.vas_user).read(['name'])
        )
        with self.assertRaises(AccessError):
            operation_type.with_user(self.vas_user).write({'name': 'Blocked'})
