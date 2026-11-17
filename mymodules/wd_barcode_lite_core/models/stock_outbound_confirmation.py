from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockOutboundConfirmation(models.Model):
    _name = 'stock.outbound.confirmation'
    _description = 'Secondary Outbound Confirmation'
    _order = 'id desc'

    picking_line_ids = fields.Many2many('stock.picking', 'stock_outbound_confirmation_picking_rel', 'confirmation_id', 'picking_id', string='Outgoing Pickings', required=True, copy=False)
    confirmation_lines = fields.One2many('stock.outbound.confirmation.line', 'confirmation_id', string='Destination Pallets', copy=False)
    unpackaged_move_line_ids = fields.Many2many('stock.move.line', 'stock_outbound_confirmation_unpacked_move_rel', 'confirmation_id', 'move_line_id', string='Unpackaged Move Lines', copy=False)
    confirmation_mode = fields.Selection([('package', 'Destination Pallet'), ('direct', 'Direct'), ('mixed', 'Destination Pallet and Direct')], required=True, string='Confirmation Mode', copy=False, index=True)
    state = fields.Selection([('scanning', 'Scanning'), ('done', 'Done'), ('cancelled', 'Cancelled')], string='Status', required=True, default='scanning', readonly=True, copy=False, index=True)
    confirmed_by_id = fields.Many2one('res.users', string='Confirmed By', readonly=True, copy=False, ondelete='restrict')
    confirmed_datetime = fields.Datetime(string='Confirmed Datetime', readonly=True, copy=False)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True, default=lambda self: self.env.company, copy=False, index=True)
    available_destination_package_line_ids = fields.Many2many('stock.quant.package', string='Available Destination Pallets', compute='_compute_available_destination_package_line_ids', store=True, readonly=True, copy=False)
    available_unpackaged_move_line_ids = fields.Many2many('stock.move.line', string='Available Unpackaged Move Lines', compute='_compute_available_unpackaged_move_line_ids', store=True, readonly=True, copy=False)

    @api.depends('picking_line_ids', 'picking_line_ids.move_line_ids.result_package_id', 'picking_line_ids.move_line_ids.state', 'picking_line_ids.move_line_ids.quantity', 'picking_line_ids.move_line_ids.secondary_outbound_confirmed')
    def _compute_available_destination_package_line_ids(self):
        move_line_model = self.env['stock.move.line']
        for rec in self:
            domain = [('picking_id', 'in', rec.picking_line_ids.ids), ('result_package_id', '!=', False), ('state', '!=', 'cancel'), ('quantity', '>', 0), ('secondary_outbound_confirmed', '=', False)]
            package_ids = move_line_model.sudo().search(domain).mapped('result_package_id').ids if rec.picking_line_ids else []
            rec.available_destination_package_line_ids = [(6, 0, package_ids)]

    @api.depends('picking_line_ids', 'picking_line_ids.move_line_ids.result_package_id', 'picking_line_ids.move_line_ids.state', 'picking_line_ids.move_line_ids.quantity', 'picking_line_ids.move_line_ids.secondary_outbound_confirmed')
    def _compute_available_unpackaged_move_line_ids(self):
        move_line_model = self.env['stock.move.line']
        for rec in self:
            domain = [('picking_id', 'in', rec.picking_line_ids.ids), ('result_package_id', '=', False), ('state', '!=', 'cancel'), ('quantity', '>', 0), ('secondary_outbound_confirmed', '=', False)]
            rec.available_unpackaged_move_line_ids = [(6, 0, move_line_model.sudo().search(domain).ids)] if rec.picking_line_ids else [(6, 0, [])]

    def action_add_all_unpackaged_move_lines(self):
        for rec in self:
            if rec.state != 'scanning':
                raise UserError(_('Only scanning confirmations can add unpackaged move lines.'))
            rec.write({'unpackaged_move_line_ids': [(6, 0, rec.available_unpackaged_move_line_ids.ids)]})
        return True

    def write(self, vals):
        if self.filtered(lambda rec: rec.state in ('done', 'cancelled')):
            raise UserError(_('Completed or cancelled secondary outbound confirmations cannot be modified.'))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda rec: rec.state in ('done', 'cancelled')):
            raise UserError(_('Completed or cancelled secondary outbound confirmations cannot be deleted.'))
        return super().unlink()

    @api.model
    def get_or_create_for_pickings(self, picking_ids):
        picking_model = self.env['stock.picking']
        picking_ids = picking_model.sudo().search([('id', 'in', picking_ids), ('picking_type_code', '=', 'outgoing'), ('state', 'not in', ('done', 'cancel'))]).ids
        pickings = picking_model.browse(picking_ids)
        if not pickings:
            raise UserError(_('No pending outgoing picking was found.'))
        pickings.check_access_rights('read')
        pickings.check_access_rule('read')
        if len(pickings.mapped('company_id')) != 1:
            raise UserError(_('Secondary outbound confirmation requires pickings from one company.'))
        confirmation_ids = self.sudo().search([('state', '=', 'scanning'), ('picking_line_ids', 'in', pickings.ids)]).ids
        for rec in self.browse(confirmation_ids):
            if set(rec.picking_line_ids.ids) == set(pickings.ids):
                return rec
        return self.create_for_pickings(pickings)

    @api.model
    def create_for_pickings(self, pickings):
        move_line_model = self.env['stock.move.line']
        move_line_ids = move_line_model.sudo().search([('picking_id', 'in', pickings.ids), ('state', '!=', 'cancel'), ('quantity', '>', 0), ('secondary_outbound_confirmed', '=', False)]).ids
        move_lines = move_line_model.browse(move_line_ids)
        if not move_lines:
            raise UserError(_('There are no pending move lines for secondary outbound confirmation.'))
        package_move_lines = move_lines.filtered('result_package_id')
        unpackaged_move_lines = move_lines - package_move_lines
        confirmation_mode = 'mixed' if package_move_lines and unpackaged_move_lines else 'package' if package_move_lines else 'direct'
        line_values = []
        for package in package_move_lines.mapped('result_package_id'):
            line_values.append((0, 0, {'destination_package_id': package.id}))
        return self.create({'picking_line_ids': [(6, 0, pickings.ids)], 'confirmation_lines': line_values, 'unpackaged_move_line_ids': [(6, 0, unpackaged_move_lines.ids)], 'confirmation_mode': confirmation_mode, 'company_id': pickings.company_id.id})

    def action_scan_destination_package(self, package_id):
        for rec in self:
            if rec.state != 'scanning':
                raise UserError(_('Only scanning confirmations can scan destination pallets.'))
            line = rec.confirmation_lines.filtered(lambda confirmation_line: confirmation_line.destination_package_id.id == package_id)
            if not line:
                raise UserError(_('This destination pallet is not pending for the current confirmation.'))
            if line.state == 'scanned':
                raise UserError(_('This destination pallet has already been scanned.'))
            self.env.cr.execute('SELECT id FROM stock_outbound_confirmation_line WHERE id = %s FOR UPDATE', [line.id])
            line.invalidate_recordset(['state'])
            if line.state == 'scanned':
                raise UserError(_('This destination pallet has already been scanned.'))
            line.write({'state': 'scanned', 'scanned_by_id': self.env.user.id, 'scanned_datetime': fields.Datetime.now()})
        return True

    def action_confirm_secondary_outbound(self, include_unpacked_lines=False):
        results = []
        for rec in self:
            if rec.state != 'scanning':
                raise UserError(_('Only scanning confirmations can be confirmed.'))
            scanned_lines = rec.confirmation_lines.filtered(lambda line: line.state == 'scanned')
            if rec.confirmation_mode in ('package', 'mixed') and not scanned_lines:
                raise UserError(_('Scan at least one destination pallet before confirming this batch.'))
            confirmed_move_lines = scanned_lines.mapped('move_line_ids')
            if rec.confirmation_mode == 'direct' or include_unpacked_lines:
                confirmed_move_lines |= rec.unpackaged_move_line_ids
            if not confirmed_move_lines:
                raise UserError(_('There are no move lines to confirm.'))
            confirmed_move_lines.write({'secondary_outbound_confirmed': True, 'outbound_confirmation_id': rec.id})
            rec.write({'state': 'done', 'confirmed_by_id': self.env.user.id, 'confirmed_datetime': fields.Datetime.now()})
            next_confirmation = rec.get_or_create_for_pickings(rec.picking_line_ids.ids) if rec.has_pending_move_lines(rec.picking_line_ids) else self.env['stock.outbound.confirmation']
            if next_confirmation:
                results.append({'confirmation_id': rec.id, 'is_final_batch': False, 'next_confirmation_id': next_confirmation.id})
                continue
            rec.picking_line_ids.action_validate_secondary_outbound()
            results.append({'confirmation_id': rec.id, 'is_final_batch': True, 'next_confirmation_id': False})
        return results[0] if len(results) == 1 else results

    def has_pending_move_lines(self, pickings):
        move_line_model = self.env['stock.move.line']
        return bool(move_line_model.sudo().search([('picking_id', 'in', pickings.ids), ('state', '!=', 'cancel'), ('quantity', '>', 0), ('secondary_outbound_confirmed', '=', False)], limit=1))


class StockOutboundConfirmationLine(models.Model):
    _name = 'stock.outbound.confirmation.line'
    _description = 'Secondary Outbound Confirmation Destination Pallet'
    _order = 'id desc'

    confirmation_id = fields.Many2one('stock.outbound.confirmation', string='Outbound Confirmation', required=True, readonly=True, ondelete='cascade', copy=False, index=True)
    destination_package_id = fields.Many2one('stock.quant.package', string='Destination Pallet', required=True, ondelete='restrict', copy=False, index=True)
    move_line_ids = fields.Many2many('stock.move.line', 'stock_outbound_confirmation_line_move_rel', 'confirmation_line_id', 'move_line_id', string='Move Lines', compute='_compute_move_line_ids', store=True, readonly=True, copy=False)
    state = fields.Selection([('pending', 'Pending'), ('scanned', 'Scanned')], string='Status', required=True, default='pending', readonly=True, copy=False, index=True)
    scanned_by_id = fields.Many2one('res.users', string='Scanned By', readonly=True, copy=False, ondelete='restrict')
    scanned_datetime = fields.Datetime(string='Scanned Datetime', readonly=True, copy=False)

    @api.depends('confirmation_id.state', 'confirmation_id.picking_line_ids', 'confirmation_id.picking_line_ids.move_line_ids.result_package_id', 'confirmation_id.picking_line_ids.move_line_ids.state', 'confirmation_id.picking_line_ids.move_line_ids.quantity', 'confirmation_id.picking_line_ids.move_line_ids.secondary_outbound_confirmed', 'confirmation_id.picking_line_ids.move_line_ids.outbound_confirmation_id', 'destination_package_id')
    def _compute_move_line_ids(self):
        move_line_model = self.env['stock.move.line']
        for rec in self:
            domain = [('picking_id', 'in', rec.confirmation_id.picking_line_ids.ids), ('result_package_id', '=', rec.destination_package_id.id), ('state', '!=', 'cancel'), ('quantity', '>', 0), ('secondary_outbound_confirmed', '=', False)]
            if rec.confirmation_id and rec.destination_package_id and rec.confirmation_id.state == 'done':
                domain[-1] = ('outbound_confirmation_id', '=', rec.confirmation_id.id)
            rec.move_line_ids = [(6, 0, move_line_model.sudo().search(domain).ids)] if rec.confirmation_id and rec.destination_package_id else [(6, 0, [])]

    @api.model_create_multi
    def create(self, vals_list):
        confirmation_ids = [vals.get('confirmation_id') for vals in vals_list if vals.get('confirmation_id')]
        confirmations = self.env['stock.outbound.confirmation'].browse(confirmation_ids)
        if confirmations.filtered(lambda confirmation: confirmation.state in ('done', 'cancelled')):
            raise UserError(_('Destination pallets cannot be added to completed or cancelled secondary outbound confirmations.'))
        return super().create(vals_list)

    def write(self, vals):
        if self.filtered(lambda rec: rec.confirmation_id.state in ('done', 'cancelled')):
            raise UserError(_('Destination pallets in completed or cancelled secondary outbound confirmations cannot be modified.'))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda rec: rec.confirmation_id.state in ('done', 'cancelled')):
            raise UserError(_('Destination pallets in completed or cancelled secondary outbound confirmations cannot be deleted.'))
        return super().unlink()
