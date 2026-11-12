# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class VasOrder(models.Model):
    _name = 'wd.vas.order'
    _description = 'Warehouse Value Add Order'
    _inherit = ['mail.thread']
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(string='VAS Order', required=True, readonly=True, copy=False, default='New')
    state = fields.Selection([('draft', 'Draft'), ('submitted', 'Submitted'), ('cancelled', 'Cancelled')], string='Status', required=True, default='draft', tracking=True, readonly=True)
    source_type = fields.Char(string='Source Type', required=True, default='manual', copy=False, index=True, tracking=True)
    source_model = fields.Char(string='Source Model', readonly=True, copy=False, index=True)
    source_record_id = fields.Integer(string='Source Record ID', readonly=True, copy=False, index=True)
    source_document_number = fields.Char(string='Source Document Number', readonly=True, copy=False, index=True)
    source_document_name = fields.Char(string='Source Document', readonly=True, copy=False)
    source_picking_id = fields.Many2one('stock.picking', string='Source Picking', readonly=True, copy=False, ondelete='restrict', index=True)
    project_id = fields.Many2one('project.project', string='Project', ondelete='restrict', index=True, tracking=True, copy=False)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', ondelete='restrict', index=True, tracking=True, copy=False)
    operator_id = fields.Many2one('res.users', string='Operator', required=True, default=lambda self: self.env.user)
    submitter_id = fields.Many2one('res.users', string='Submitter', readonly=True, tracking=True)
    submitted_at = fields.Datetime(string='Submitted At', readonly=True, tracking=True)
    unsubmitted_by = fields.Many2one('res.users', string='Unsubmitted By', readonly=True, tracking=True)
    unsubmitted_at = fields.Datetime(string='Unsubmitted At', readonly=True, tracking=True)
    cancelled_by = fields.Many2one('res.users', string='Cancelled By', readonly=True, tracking=True)
    cancelled_at = fields.Datetime(string='Cancelled At', readonly=True, tracking=True)
    cancel_reason = fields.Text(string='Cancel Reason', tracking=True)
    line_ids = fields.One2many('wd.vas.order.line', 'order_id', string='Lines')
    attachment_ids = fields.Many2many('ir.attachment', 'wd_vas_order_attachment_rel', 'order_id', 'attachment_id', string='Attachments')
    notes = fields.Text(string='Notes', tracking=True)
    outbound_palletization_id = fields.Many2one('wd.vas.outbound.palletization', string='Outbound Palletization', readonly=True, copy=False, ondelete='set null', index=True)
    has_outbound_palletization_operation = fields.Boolean(string='Has Outbound Palletization', compute='_compute_has_outbound_palletization_operation', store=True, readonly=True)

    _PROTECTED_WRITE_FIELDS = frozenset({'state', 'source_type', 'source_model', 'source_record_id', 'source_document_number', 'source_document_name', 'source_picking_id', 'project_id', 'warehouse_id', 'operator_id', 'submitter_id', 'submitted_at', 'unsubmitted_by', 'unsubmitted_at', 'cancelled_by', 'cancelled_at', 'cancel_reason', 'line_ids', 'attachment_ids', 'notes'})

    @api.depends('line_ids.operation_type_id.is_outbound_palletization')
    def _compute_has_outbound_palletization_operation(self):
        for rec in self:
            rec.has_outbound_palletization_operation = any(rec.line_ids.mapped('operation_type_id.is_outbound_palletization'))

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = sequence.next_by_code('wd.vas.order') or 'New'
        return super().create(vals_list)

    def lock_for_update(self):
        records = self.sorted('id')
        if records:
            self.env.cr.execute('SELECT id FROM wd_vas_order WHERE id IN %s FOR UPDATE', [tuple(records.ids)])
            records.invalidate_recordset()
        return records

    def action_write(self, vals):
        return super(VasOrder, self).write(vals)

    def get_source_submit_values(self):
        for rec in self:
            raise ValidationError('No VAS source adapter is installed for this work order.')

    def get_outbound_palletization_pickings(self):
        picking_model = self.env['stock.picking']
        picking_ids = []
        for rec in self:
            if rec.source_picking_id:
                picking_ids += picking_model.sudo().search([('id', '=', rec.source_picking_id.id), ('picking_type_id.code', '=', 'outgoing'), ('state', 'not in', ('done', 'cancel'))], order='id').ids
        return picking_model.browse(picking_ids)

    def action_start_outbound_palletization(self):
        palletization_results = []
        for rec in self:
            rec.check_action_access()
            if rec.state == 'cancelled':
                raise UserError(_('Cancelled VAS Orders cannot start palletization.'))
            if not rec.has_outbound_palletization_operation:
                raise UserError(_('Add an outbound palletization operation before starting palletization.'))
            picking_ids = rec.get_outbound_palletization_pickings()
            if not picking_ids:
                raise UserError(_('The VAS Order has no active outbound picking.'))
            if not rec.project_id.outbound_palletization_enabled:
                raise UserError(_('Enable Outbound Palletization and Secondary Confirmation on the project first.'))
            unprepared_pickings = picking_ids.filtered(lambda picking: picking.outbound_preparation_state != 'prepared')
            if unprepared_pickings:
                raise UserError(_('Complete outbound picking first. The following pickings are not prepared: %s.') % ', '.join(unprepared_pickings.mapped('name')))
            palletization = rec.outbound_palletization_id
            if not palletization or palletization.state == 'cancelled':
                palletization = self.env['wd.vas.outbound.palletization'].create({'vas_order_id': rec.id, 'picking_ids': [(6, 0, picking_ids.ids)]})
                rec.write({'outbound_palletization_id': palletization.id})
            palletization_results.append({'success': True, 'palletization_id': palletization.id, 'state': palletization.state})
        return palletization_results[0] if len(palletization_results) == 1 else palletization_results

    def action_open_outbound_palletization(self):
        for rec in self:
            result = rec.action_start_outbound_palletization()
            return {'type': 'ir.actions.act_window', 'res_model': 'wd.vas.outbound.palletization', 'res_id': result['palletization_id'], 'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current'}
        return False

    def action_open_transport_pallet_create_wizard(self):
        for rec in self:
            result = rec.action_start_outbound_palletization()
            return {'type': 'ir.actions.act_window', 'name': _('Create Transport Pallets'), 'res_model': 'wd.vas.transport.pallet.create.wizard', 'view_mode': 'form', 'views': [(False, 'form')], 'target': 'new', 'context': {'default_palletization_id': result['palletization_id']}}
        return False

    def action_print_transport_pallet_labels(self):
        for rec in self:
            rec.check_action_access()
            if not rec.outbound_palletization_id:
                raise UserError(_('Create transport pallets before printing labels.'))
            return rec.outbound_palletization_id.action_print_transport_pallet_labels()
        return False

    def validate_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise ValidationError('Only Draft VAS Orders can be submitted.')
            if not rec.operator_id or not rec.operator_id.active or not (rec.operator_id.has_group('wd_warehouse_value_add.group_vas_user') or rec.operator_id.has_group('wd_warehouse_value_add.group_vas_manager')):
                raise ValidationError('An active Operator is required.')
            if not rec.line_ids:
                raise ValidationError('At least one VAS Order line is required.')
            for line in rec.line_ids:
                if not line.operation_type_id or not line.operation_type_id.active:
                    raise ValidationError('Each line must use an active Operation Type.')
                if not line.unit or line.unit != line.operation_type_id.unit:
                    raise ValidationError('Each line unit must match its Operation Type.')
                if line.quantity_time is None or line.quantity_time <= 0:
                    raise ValidationError('Each line quantity or time must be greater than zero.')

    def action_submit(self):
        self.check_action_access()
        for rec in self:
            rec.lock_for_update()
            if rec.has_outbound_palletization_operation and rec.outbound_palletization_id.state == 'in_progress':
                raise UserError(_('Complete or reset outbound palletization before submitting this VAS Order.'))
            rec.validate_submit()
            source_values = rec.get_source_submit_values()
            rec.action_write({**source_values, 'submitter_id': self.env.user.id, 'submitted_at': fields.Datetime.now(), 'state': 'submitted'})
        return True

    def action_unsubmit(self):
        self.check_action_access()
        for rec in self:
            rec.lock_for_update()
            if rec.state != 'submitted':
                raise ValidationError('Only Submitted VAS Orders can be unsubmitted.')
            rec.action_write({'unsubmitted_by': self.env.user.id, 'unsubmitted_at': fields.Datetime.now(), 'state': 'draft'})
        return True

    def action_cancel(self, reason=None):
        self.check_action_access()
        for rec in self:
            rec.lock_for_update()
            if rec.state != 'draft':
                raise ValidationError('Only Draft VAS Orders can be cancelled.')
            cancel_reason = (reason if reason is not None else rec.cancel_reason or '').strip()
            if not cancel_reason:
                raise ValidationError('A cancellation reason is required.')
            rec.action_write({'cancel_reason': cancel_reason, 'cancelled_by': self.env.user.id, 'cancelled_at': fields.Datetime.now(), 'state': 'cancelled'})
        return True

    def unlink(self):
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError('Only cancelled VAS Orders can be deleted.')
        return super().unlink()

    def check_action_access(self):
        for rec in self:
            if rec.env.is_superuser() or rec.env.user.has_group('wd_warehouse_value_add.group_vas_user') or rec.env.user.has_group('wd_warehouse_value_add.group_vas_manager'):
                continue
            raise AccessError('You do not have permission to perform this VAS action.')

    def write(self, vals):
        for rec in self:
            rec.lock_for_update()
            if rec.state in ('submitted', 'cancelled') and self._PROTECTED_WRITE_FIELDS.intersection(vals):
                raise ValidationError('Submitted or Cancelled VAS Orders cannot be modified.')
        return super().write(vals)

    @api.constrains('name')
    def check_name_unique(self):
        for rec in self:
            duplicate = self.sudo().search([('name', '=', rec.name), ('id', '!=', rec.id)], limit=1)
            if duplicate:
                raise ValidationError('VAS order name must be unique.')
