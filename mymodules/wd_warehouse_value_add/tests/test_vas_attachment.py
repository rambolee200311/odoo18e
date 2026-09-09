# -*- coding: utf-8 -*-

import base64
from uuid import uuid4

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestVasAttachment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.VasOrder = cls.env['wd.vas.order']
        cls.Attachment = cls.env['ir.attachment']
        cls.InboundOrder = cls.env['world.depot.inbound.order']
        cls.Project = cls.env['project.project']
        cls.Currency = cls.env['res.currency']
        cls.ChargeUnit = cls.env['world.depot.charge.unit']
        cls.OperationType = cls.env['wd.vas.operation.type']
        cls.warehouse = cls.env['stock.warehouse'].search([], limit=1)
        cls.operator = cls.env['res.users'].search(
            [('active', '=', True), ('share', '=', False)],
            limit=1,
        )
        cls.user_group = cls.env.ref('wd_warehouse_value_add.group_vas_user')
        cls.env.user.write({'groups_id': [(4, cls.user_group.id)]})
        cls.operator.write({'groups_id': [(4, cls.user_group.id)]})
        cls.project = cls.Project.search([], limit=1)
        cls.currency = cls.Currency.search([], limit=1)
        cls.unit = cls.ChargeUnit.create({'name': 'Attachment Test Unit'})
        cls.operation_type = cls.OperationType.create({
            'name': 'Attachment Test Operation',
            'code': 'ATT-%s' % uuid4().hex[:8],
            'unit_id': cls.unit.id,
        })

    def _order(self):
        return self.VasOrder.create({
            'order_type': 'inbound',
            'warehouse_order_billno': 'ATT-%s' % uuid4().hex[:8],
            'warehouse_id': self.warehouse.id,
            'operator_id': self.operator.id,
        })

    def test_draft_attachment_is_editable_and_locked_after_submit(self):
        order = self._order()
        attachment = self.Attachment.create({
            'name': 'vas-proof.txt',
            'type': 'binary',
            'datas': base64.b64encode(b'proof'),
            'res_model': 'wd.vas.order',
            'res_id': order.id,
        })
        order.write({'attachment_ids': [(4, attachment.id)]})
        self.assertIn(attachment, order.attachment_ids)

        warehouse_order = self.InboundOrder.create({
            'billno': 'ATT-IN-%s' % uuid4().hex[:8],
            'type': 'inbound',
            'date': '2026-09-07',
            'project': self.project.id,
            'reference': 'VAS attachment test',
            'currency_id': self.currency.id,
            'warehouse': self.warehouse.id,
            'state': 'confirm',
        })
        order.write({'warehouse_order_billno': warehouse_order.billno})
        self.env['wd.vas.order.line'].create({
            'order_id': order.id,
            'operation_type_id': self.operation_type.id,
            'quantity_time': 1,
        })
        order.action_submit()
        with self.assertRaises(ValidationError):
            order.write({'attachment_ids': [(3, attachment.id)]})
