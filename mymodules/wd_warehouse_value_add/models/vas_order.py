# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class VasOrder(models.Model):
    _name = 'wd.vas.order'
    _description = 'Warehouse Value Add Order'
    _inherit = ['mail.thread']
    _rec_name = 'name'
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='VAS Order',
        required=True,
        readonly=True,
        copy=False,
        default='New',
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        required=True,
        default='draft',
        tracking=True,
        readonly=True,
    )
    order_type = fields.Selection(
        [
            ('inbound', 'Inbound'),
            ('outbound', 'Outbound'),
            ('transfer', 'Transfer'),
        ],
        string='Warehouse Order Type',
        required=True,
        tracking=True,
    )
    inbound_order_id = fields.Many2one(
        'world.depot.inbound.order',
        string='Inbound Order',
        ondelete='restrict',
        tracking=True,
    )
    outbound_order_id = fields.Many2one(
        'world.depot.outbound.order',
        string='Outbound Order',
        ondelete='restrict',
        tracking=True,
    )
    transfer_order_id = fields.Many2one(
        'world.depot.transfer.order',
        string='Transfer Order',
        ondelete='restrict',
        tracking=True,
    )
    warehouse_order_billno = fields.Char(
        string='Warehouse Order Bill No.',
    )
    project_id = fields.Many2one('project.project', string='Project', ondelete='restrict', index=True, tracking=True, copy=False)
    warehouse_order_display = fields.Char(
        string='Warehouse Order',
        compute='_compute_warehouse_order_display',
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        ondelete='restrict',
    )
    operator_id = fields.Many2one(
        'res.users',
        string='Operator',
        required=True,
        default=lambda self: self.env.user,
    )
    submitter_id = fields.Many2one(
        'res.users',
        string='Submitter',
        readonly=True,
        tracking=True,
    )
    submitted_at = fields.Datetime(
        string='Submitted At',
        readonly=True,
        tracking=True,
    )
    unsubmitted_by = fields.Many2one(
        'res.users',
        string='Unsubmitted By',
        readonly=True,
        tracking=True,
    )
    unsubmitted_at = fields.Datetime(
        string='Unsubmitted At',
        readonly=True,
        tracking=True,
    )
    cancelled_by = fields.Many2one(
        'res.users',
        string='Cancelled By',
        readonly=True,
        tracking=True,
    )
    cancelled_at = fields.Datetime(
        string='Cancelled At',
        readonly=True,
        tracking=True,
    )
    cancel_reason = fields.Text(
        string='Cancel Reason',
        tracking=True,
    )
    line_ids = fields.One2many(
        'wd.vas.order.line',
        'order_id',
        string='Lines',
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'wd_vas_order_attachment_rel',
        'order_id',
        'attachment_id',
        string='Attachments',
    )
    notes = fields.Text(string='Notes', tracking=True)

    _PROTECTED_WRITE_FIELDS = frozenset({
        'state',
        'order_type',
        'inbound_order_id',
        'outbound_order_id',
        'transfer_order_id',
        'warehouse_order_billno',
        'project_id',
        'warehouse_id',
        'operator_id',
        'submitter_id',
        'submitted_at',
        'unsubmitted_by',
        'unsubmitted_at',
        'cancelled_by',
        'cancelled_at',
        'cancel_reason',
        'line_ids',
        'attachment_ids',
        'notes',
    })

    _RELATION_BY_ORDER_TYPE = {
        'inbound': ('inbound_order_id', 'world.depot.inbound.order'),
        'outbound': ('outbound_order_id', 'world.depot.outbound.order'),
        'transfer': ('transfer_order_id', 'world.depot.transfer.order'),
    }

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = sequence.next_by_code('wd.vas.order') or 'New'
        return super().create(vals_list)

    @api.onchange('order_type', 'warehouse_order_billno')
    def onchange_warehouse_order_billno(self):
        for record in self:
            relation = record._RELATION_BY_ORDER_TYPE.get(record.order_type)
            billno = (record.warehouse_order_billno or '').strip()
            if not relation or not billno:
                record.project_id = False
                record.warehouse_id = False
                continue
            warehouse_orders = record.env[relation[1]].sudo().search([
                ('billno', '=', billno),
            ], limit=2)
            record.project_id = warehouse_orders.project if len(warehouse_orders) == 1 else False
            record.warehouse_id = warehouse_orders.warehouse if len(warehouse_orders) == 1 else False

    @api.onchange('order_type', 'inbound_order_id', 'outbound_order_id', 'transfer_order_id')
    def onchange_warehouse_order_relation(self):
        for record in self:
            relation = record._RELATION_BY_ORDER_TYPE.get(record.order_type)
            relation_fields = tuple(item[0] for item in record._RELATION_BY_ORDER_TYPE.values())
            if not relation:
                for field_name in relation_fields:
                    record[field_name] = False
                continue
            relation_field = relation[0]
            for field_name in relation_fields:
                if field_name != relation_field:
                    record[field_name] = False
            warehouse_order = record[relation_field]
            if warehouse_order:
                record.warehouse_order_billno = warehouse_order.billno
                record.project_id = warehouse_order.project
                record.warehouse_id = warehouse_order.warehouse

    def _lock_for_update(self):
        records = self.sorted('id')
        if not records:
            return records
        self.env.cr.execute(
            'SELECT id FROM wd_vas_order WHERE id IN %s FOR UPDATE',
            [tuple(records.ids)],
        )
        records.invalidate_recordset()
        return records

    def _lock_warehouse_order(self, warehouse_order):
        self.env.cr.execute(
            'SELECT id FROM "%s" WHERE id = %%s FOR UPDATE'
            % warehouse_order._table,
            [warehouse_order.id],
        )
        warehouse_order.invalidate_recordset(
            ['state', 'billno', 'warehouse', 'project'],
        )
        return warehouse_order

    def _action_write(self, vals):
        return super(VasOrder, self).write(vals)

    def _get_warehouse_order(self):
        self.ensure_one()
        relation = self._RELATION_BY_ORDER_TYPE.get(self.order_type)
        if not relation:
            raise ValidationError('Warehouse Order type is invalid.')

        billno = (self.warehouse_order_billno or '').strip()
        if not billno:
            raise ValidationError('Warehouse Order bill number is required.')
        if billno != self.warehouse_order_billno:
            self._action_write({'warehouse_order_billno': billno})

        warehouse_order_model = self.env[relation[1]].sudo()
        warehouse_orders = warehouse_order_model.search([
            ('billno', '=', billno),
        ])
        if not warehouse_orders:
            raise ValidationError(
                'No Warehouse Order was found for the specified type and bill number.'
            )
        if len(warehouse_orders) > 1:
            raise ValidationError(
                'More than one Warehouse Order matches the specified type and bill number.'
            )
        return self._lock_warehouse_order(warehouse_orders)

    def _validate_submit(self):
        self.ensure_one()
        if self.state != 'draft':
            raise ValidationError('Only Draft VAS Orders can be submitted.')
        if (
            not self.operator_id
            or not self.operator_id.active
            or not (
                self.operator_id.has_group(
                    'wd_warehouse_value_add.group_vas_user'
                )
                or self.operator_id.has_group(
                    'wd_warehouse_value_add.group_vas_manager'
                )
            )
        ):
            raise ValidationError('An active Operator is required.')
        if not self.line_ids:
            raise ValidationError('At least one VAS Order line is required.')
        for line in self.line_ids:
            if not line.operation_type_id or not line.operation_type_id.active:
                raise ValidationError(
                    'Each line must use an active Operation Type.'
                )
            if not line.unit or line.unit != line.operation_type_id.unit:
                raise ValidationError(
                    'Each line unit must match its Operation Type.'
                )
            if line.quantity_time is None or line.quantity_time <= 0:
                raise ValidationError(
                    'Each line quantity or time must be greater than zero.'
                )

    def action_submit(self):
        self.ensure_one()
        self._check_action_access()
        self._lock_for_update()
        self._validate_submit()
        warehouse_order = self._get_warehouse_order()
        if warehouse_order.state == 'cancel':
            raise ValidationError(
                'A cancelled Warehouse Order cannot be submitted.'
            )
        if not warehouse_order.warehouse:
            raise ValidationError(
                'The linked Warehouse Order has no warehouse configured and cannot be submitted.'
            )
        if self.project_id != warehouse_order.project:
            raise ValidationError(
                'VAS Order Project must match the Warehouse Order Project.'
            )
        relation_field = self._RELATION_BY_ORDER_TYPE[self.order_type][0]
        relation_values = {
            'inbound_order_id': False,
            'outbound_order_id': False,
            'transfer_order_id': False,
            relation_field: warehouse_order.id,
            'warehouse_order_billno': warehouse_order.billno,
            'warehouse_id': warehouse_order.warehouse.id,
            'submitter_id': self.env.user.id,
            'submitted_at': fields.Datetime.now(),
            'state': 'submitted',
        }
        self._action_write(relation_values)
        return True

    def action_unsubmit(self):
        self.ensure_one()
        self._check_action_access()
        self._lock_for_update()
        if self.state != 'submitted':
            raise ValidationError(
                'Only Submitted VAS Orders can be unsubmitted.'
            )
        self._action_write({
            'unsubmitted_by': self.env.user.id,
            'unsubmitted_at': fields.Datetime.now(),
            'state': 'draft',
        })
        return True

    def action_cancel(self, reason=None):
        self.ensure_one()
        self._check_action_access()
        self._lock_for_update()
        if self.state != 'draft':
            raise ValidationError('Only Draft VAS Orders can be cancelled.')
        cancel_reason = (reason if reason is not None else self.cancel_reason or '').strip()
        if not cancel_reason:
            raise ValidationError('A cancellation reason is required.')
        self._action_write({
            'cancel_reason': cancel_reason,
            'cancelled_by': self.env.user.id,
            'cancelled_at': fields.Datetime.now(),
            'state': 'cancelled',
        })
        return True

    def _check_action_access(self):
        if self.env.is_superuser() or self.env.user.has_group(
            'wd_warehouse_value_add.group_vas_user'
        ) or self.env.user.has_group(
            'wd_warehouse_value_add.group_vas_manager'
        ):
            return
        raise AccessError('You do not have permission to perform this VAS action.')

    def write(self, vals):
        for record in self:
            record._lock_for_update()
            if (
                record.state in ('submitted', 'cancelled')
                and self._PROTECTED_WRITE_FIELDS.intersection(vals)
            ):
                raise ValidationError(
                    'Submitted or Cancelled VAS Orders cannot be modified.'
                )
        return super().write(vals)

    @api.constrains('name')
    def _check_name_unique(self):
        for record in self:
            duplicate = self.search([
                ('name', '=', record.name),
                ('id', '!=', record.id),
            ], limit=1)
            if duplicate:
                raise ValidationError('VAS order name must be unique.')

    @api.depends(
        'inbound_order_id',
        'outbound_order_id',
        'transfer_order_id',
    )
    def _compute_warehouse_order_display(self):
        for record in self:
            order = (
                record.inbound_order_id
                or record.outbound_order_id
                or record.transfer_order_id
            )
            record.warehouse_order_display = order.display_name if order else False

    @api.constrains(
        'order_type',
        'inbound_order_id',
        'outbound_order_id',
        'transfer_order_id',
    )
    def _check_order_relation_consistency(self):
        relation_by_type = {
            'inbound': 'inbound_order_id',
            'outbound': 'outbound_order_id',
            'transfer': 'transfer_order_id',
        }
        relation_fields = tuple(relation_by_type.values())
        for record in self:
            populated = [
                field_name
                for field_name in relation_fields
                if record[field_name]
            ]
            if len(populated) > 1:
                raise ValidationError(
                    'Only one Warehouse Order relation may be set.'
                )
            expected_field = relation_by_type.get(record.order_type)
            if populated and populated[0] != expected_field:
                raise ValidationError(
                    'Warehouse Order relation must match the selected order type.'
                )
