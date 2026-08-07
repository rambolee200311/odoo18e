# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


# =====================================================================
# Transport Event — 动态运输事件（8 类型 + 3 层时间 + 时序约束）
# =====================================================================
class TransportEvent(models.Model):
    _name = 'tlmp.transport.event'
    _description = 'Transport Event'
    _order = 'order_id, sequence, planned_time'
    _rec_name = 'display_name'

    order_id = fields.Many2one('tlmp.transport.order', string='Transport Order',
                               required=True, index=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    event_type_id = fields.Many2one(
        'tlmp.transport.event.type', string='Event Type', required=True)
    event_state = fields.Selection([
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('skipped', 'Skipped'),
        ('cancelled', 'Cancelled'),
    ], string='Status', required=True, default='pending')
    location = fields.Char(string='Location')
    operator = fields.Char(string='Operator')
    notes = fields.Text(string='Notes')

    # 3-layer time
    planned_time = fields.Datetime(string='Planned Time')
    estimated_time = fields.Datetime(string='Estimated Time')
    actual_time = fields.Datetime(string='Actual Time')

    # Skip/Cancel reason (required for skipped/cancelled)
    skip_cancel_reason = fields.Text(string='Skip/Cancel Reason')

    # Attachments
    attachment_ids = fields.Many2many(
        'ir.attachment', 'transport_event_attachment_rel',
        'event_id', 'attachment_id', string='Attachments')

    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)

    @api.depends('event_type_id', 'event_state', 'sequence')
    def _compute_display_name(self):
        for r in self:
            r.display_name = '%s - %s' % (r.get_event_type_id_label(), r.get_event_state_label())

    def get_event_type_id_label(self):
        return dict(self._fields['event_type_id'].selection).get(self.event_type_id, self.event_type_id)

    def get_event_state_label(self):
        return dict(self._fields['event_state'].selection).get(self.event_state, self.event_state)

    # ── Constraint: skip_cancel_reason required ──
    @api.constrains('event_state', 'skip_cancel_reason')
    def _check_skip_cancel_reason(self):
        for r in self:
            if r.event_state in ('skipped', 'cancelled') and not r.skip_cancel_reason:
                raise ValidationError(_(
                    'Skip/Cancel reason is required when event status is "%s".'
                ) % r.get_event_state_label())

    # ── Constraint: base event sequential ordering ──
    def _get_scene_event_type_ids(self):
        """Return ordered event type IDs for this order's scene."""
        self.ensure_one()
        if not self.order_id or not self.order_id.scene_id:
            return []
        paths = self.env['tlmp.transport.scene.event'].search([
            ('scene_id', '=', self.order_id.scene_id.id),
            ('active', '=', True),
        ], order='sequence, id')
        return list(paths.mapped('event_type_id.id'))

    @api.constrains('event_type_id', 'sequence', 'event_state')
    def _check_sequential_order(self):
        for r in self:
            if not r.event_type_id or r.event_state == 'cancelled':
                continue
            if not r.event_type_id.is_base_event:
                continue
            event_order = r._get_scene_event_type_ids()
            if not event_order:
                continue
            try:
                pos = event_order.index(r.event_type_id.id)
            except ValueError:
                return
            later_ids = event_order[pos + 1:]
            if not later_ids:
                return
            later_events = self.search([
                ('order_id', '=', r.order_id.id),
                ('event_type_id', 'in', later_ids),
                ('id', '!=', r.id),
                ('event_state', 'not in', ('cancelled',)),
            ])
            if later_events:
                raise ValidationError(_(
                    'Cannot record event after "%s" has already occurred.'
                ) % later_events[0].event_type_id.name)

    @api.constrains('event_type_id', 'event_state', 'attachment_ids')
    def _check_pod_attachment(self):
        for r in self:
            if r.event_type_id and r.event_type_id.code == 'DELIVERY_COMPLETED' and r.event_state == 'completed':
                if not r.attachment_ids:
                    raise ValidationError(_(
                        'POD attachment is required to complete the Delivery Completed event.'
                    ))

    # ── No physical deletion ──
    def unlink(self):
        for r in self:
            raise UserError(_(
                'Transport events cannot be deleted. '
                'Use "Skipped" or "Cancelled" status to mark events as inactive.'
            ))

    # ── State transitions ──
    def action_set_pending(self):
        self.write({'event_state': 'pending'})

    def action_set_in_progress(self):
        self.write({'event_state': 'in_progress', 'actual_time': fields.Datetime.now()})

    def action_complete(self):
        self.write({'event_state': 'completed', 'actual_time': fields.Datetime.now()})

    def action_skip(self):
        self.write({'event_state': 'skipped'})

    def action_cancel(self):
        self.write({'event_state': 'cancelled'})

    # ── 3-layer time auto-set ──
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('planned_time'):
                vals['planned_time'] = fields.Datetime.now()
        return super().create(vals_list)


# =====================================================================
# Transport Exception — 运输异常（4 态 + 12 类型）
# =====================================================================
class TransportException(models.Model):
    _name = 'tlmp.transport.exception'
    _description = 'Transport Exception'
    _order = 'order_id, create_date desc'
    _rec_name = 'display_name'

    order_id = fields.Many2one('tlmp.transport.order', string='Transport Order',
                               required=True, index=True, ondelete='cascade')
    event_id = fields.Many2one('tlmp.transport.event', string='Related Event',
                               index=True, ondelete='set null')
    exception_type = fields.Selection([
        ('damage_shortage', 'Cargo Damage / Shortage'),
        ('vehicle_breakdown', 'Vehicle Breakdown'),
        ('traffic_delay', 'Traffic Congestion Delay'),
        ('wrong_pickup', 'Wrong Pickup'),
        ('customer_rejected', 'Customer Rejected'),
        ('container_damage', 'Container Damage'),
        ('empty_overdue', 'Empty Container Overdue'),
        ('customs_hold', 'Customs Hold / Inspection'),
        ('t1_overdue', 'T1 Transit Overdue'),
        ('mrn_mismatch', 'MRN Declaration Mismatch'),
        ('adr_driver_unqualified', 'ADR Driver Unqualified'),
        ('adr_packaging', 'DG Packaging Non-compliant'),
    ], string='Exception Type', required=True)
    exception_state = fields.Selection([
        ('open', 'Open'),
        ('processing', 'Processing'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ], string='Status', required=True, default='open')
    description = fields.Text(string='Description', required=True)
    carrier_feedback = fields.Text(string='Carrier Feedback')
    handler = fields.Char(string='Handler')
    resolution = fields.Text(string='Resolution')
    indemnity_amount = fields.Monetary(string='Indemnity Amount')
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.company.currency_id)
    resolved_time = fields.Datetime(string='Resolved Time')
    closed_time = fields.Datetime(string='Closed Time')
    attachment_ids = fields.Many2many(
        'ir.attachment', 'transport_exception_attachment_rel',
        'exception_id', 'attachment_id', string='Attachments')

    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)

    @api.depends('exception_type', 'exception_state')
    def _compute_display_name(self):
        for r in self:
            r.display_name = '%s [%s]' % (r.get_exception_type_label(), r.get_exception_state_label())

    def get_exception_type_label(self):
        return dict(self._fields['exception_type'].selection).get(self.exception_type, self.exception_type)

    def get_exception_state_label(self):
        return dict(self._fields['exception_state'].selection).get(self.exception_state, self.exception_state)

    # ── State transitions ──
    def action_process(self):
        self.write({'exception_state': 'processing'})

    def action_resolve(self):
        self.write({'exception_state': 'resolved', 'resolved_time': fields.Datetime.now()})

    def action_close(self):
        self.write({'exception_state': 'closed', 'closed_time': fields.Datetime.now()})

    def action_reopen(self):
        self.write({'exception_state': 'processing'})

    # ── No physical deletion ──
    def unlink(self):
        raise UserError(_('Transport exceptions cannot be deleted. '
                          'Use status transitions to manage lifecycle.'))


# =====================================================================
# Extra Charge — 途中额外费用台账（9 类型）
# =====================================================================
class ExtraCharge(models.Model):
    _name = 'tlmp.transport.extra.charge'
    _description = 'Extra Charge'
    _order = 'order_id, create_date desc'
    _rec_name = 'display_name'

    order_id = fields.Many2one('tlmp.transport.order', string='Transport Order',
                               required=True, index=True, ondelete='cascade')
    event_id = fields.Many2one('tlmp.transport.event', string='Related Event',
                               index=True, ondelete='set null')
    charge_type = fields.Selection([
        ('detention', 'Detention (container)'),
        ('waiting', 'Waiting (truck)'),
        ('customs_fee', 'Customs Fee'),
        ('express_delivery', 'Express Delivery Surcharge'),
        ('loading_extra', 'Loading/Unloading Extra'),
        ('empty_return', 'Empty Container Round Trip'),
        ('damage_handling', 'Cargo Damage Handling'),
        ('adr_service', 'ADR Compliance Service'),
        ('bonded_service', 'Bonded Declaration Service'),
    ], string='Charge Type', required=True)
    amount = fields.Monetary(string='Amount', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.company.currency_id)
    quantity = fields.Float(string='Quantity', default=1.0)
    uom = fields.Char(string='Unit of Measure')
    reason = fields.Text(string='Reason')
    party_type = fields.Selection([
        ('customer', 'Customer'),
        ('us', 'Our Side'),
        ('carrier', 'Carrier'),
    ], string='Charge Party', required=True, default='us')
    attachment_ids = fields.Many2many(
        'ir.attachment', 'extra_charge_attachment_rel',
        'charge_id', 'attachment_id', string='Attachments')

    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)

    @api.depends('charge_type', 'amount')
    def _compute_display_name(self):
        for r in self:
            r.display_name = '%s: %.2f' % (r.get_charge_type_label(), r.amount or 0.0)

    def get_charge_type_label(self):
        return dict(self._fields['charge_type'].selection).get(self.charge_type, self.charge_type)
