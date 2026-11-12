# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class VasOutboundPalletization(models.Model):
    _name = 'wd.vas.outbound.palletization'
    _description = 'VAS Outbound Palletization'
    _order = 'id desc'

    name = fields.Char(string='Palletization Number', required=True, readonly=True, copy=False, default='New')
    vas_order_id = fields.Many2one('wd.vas.order', string='VAS Order', required=True, readonly=True, copy=False, ondelete='cascade', index=True)
    picking_ids = fields.Many2many('stock.picking', 'wd_vas_outbound_palletization_picking_rel', 'palletization_id', 'picking_id', string='Outbound Pickings', required=True, readonly=True)
    state = fields.Selection([('pending', 'Pending'), ('in_progress', 'In Progress'), ('validated', 'Validated'), ('cancelled', 'Cancelled')], string='Status', required=True, default='pending', readonly=True, copy=False, index=True)
    palletization_lines = fields.One2many('wd.vas.outbound.palletization.line', 'palletization_id', string='Palletization Lines', copy=False)
    transport_pallet_ids = fields.One2many('stock.quant.package', 'vas_outbound_palletization_id', string='Transport Pallets', readonly=True, copy=False)
    started_by_id = fields.Many2one('res.users', string='Started By', readonly=True, copy=False, ondelete='restrict')
    started_at = fields.Datetime(string='Started At', readonly=True, copy=False)
    validated_by_id = fields.Many2one('res.users', string='Validated By', readonly=True, copy=False, ondelete='restrict')
    validated_at = fields.Datetime(string='Validated At', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = sequence.next_by_code('wd.vas.outbound.palletization') or 'New'
        return super().create(vals_list)

    def lock_for_update(self):
        records = self.sorted('id')
        if records:
            self.env.cr.execute('SELECT id FROM wd_vas_outbound_palletization WHERE id IN %s FOR UPDATE', [tuple(records.ids)])
            records.invalidate_recordset()
        return records

    def get_picking_move_lines(self):
        move_line_model = self.env['stock.move.line']
        move_lines = move_line_model
        for rec in self:
            move_line_ids = move_line_model.sudo().search([('picking_id', 'in', rec.picking_ids.ids), ('state', '!=', 'cancel'), ('quantity', '>', 0)], order='id').ids
            move_lines |= move_line_model.browse(move_line_ids)
        return move_lines

    def get_validation_error(self):
        for rec in self:
            if not rec.picking_ids:
                return 'At least one outbound picking is required.'
            completed_pickings = rec.picking_ids.filtered(lambda picking: picking.state in ('done', 'cancel'))
            if completed_pickings:
                return 'Validated or cancelled outbound pickings cannot be palletized: %s.' % ', '.join(completed_pickings.mapped('name'))
        return False

    def action_validate_palletization(self):
        for rec in self:
            rec.lock_for_update()
            if rec.state != 'in_progress':
                raise UserError('Only an in-progress palletization can be validated.')
            validation_error = rec.get_validation_error()
            if validation_error:
                raise UserError(validation_error)
            move_lines = rec.get_picking_move_lines()
            allocations = rec.palletization_lines.sorted('id')
            if not move_lines or not allocations:
                raise UserError('Scan palletization allocations before validation.')
            allocations_by_move_line = defaultdict(lambda: self.env['wd.vas.outbound.palletization.line'])
            for allocation in allocations:
                source_move_line = allocation.source_move_line_id
                if source_move_line not in move_lines:
                    raise UserError('A palletization allocation no longer belongs to this work order pickings.')
                if allocation.source_package_id != source_move_line.package_id or allocation.product_id != source_move_line.product_id or allocation.lot_id != source_move_line.lot_id:
                    raise UserError('A palletization allocation no longer matches its picked source line.')
                if not allocation.destination_package_id or allocation.quantity <= 0:
                    raise UserError('Every picked quantity must be assigned to a destination pallet.')
                if allocation.handling_type == 'direct_outbound' and (not allocation.source_package_id or allocation.destination_package_id != allocation.source_package_id):
                    raise UserError('Direct outbound is only allowed when the complete source pallet remains unchanged.')
                if allocation.handling_type == 'palletize' and allocation.destination_package_id == allocation.source_package_id:
                    raise UserError('Palletized goods must be assigned to a different destination pallet.')
                if allocation.handling_type == 'palletize' and allocation.destination_package_id.vas_outbound_palletization_id != rec:
                    raise UserError('Palletized goods must use a transport pallet created for this palletization.')
                allocations_by_move_line[source_move_line.id] |= allocation
            if set(allocations_by_move_line) != set(move_lines.ids):
                raise UserError('Palletization must cover every picked line exactly.')
            for move_line in move_lines:
                rows = allocations_by_move_line[move_line.id]
                rounding = move_line.product_uom_id.rounding or move_line.product_id.uom_id.rounding
                if float_compare(sum(rows.mapped('quantity')), move_line.quantity, precision_rounding=rounding) != 0:
                    raise UserError('Palletization quantity does not match the picked quantity for %s.' % move_line.product_id.display_name)
                if move_line.product_id.tracking == 'serial' and (len(rows) != 1 or float_compare(rows.quantity, 1.0, precision_rounding=rounding) != 0):
                    raise UserError('A serial number must remain on one destination pallet.')
            for source_package in allocations.filtered(lambda line: line.handling_type == 'direct_outbound').mapped('source_package_id'):
                package_move_lines = move_lines.filtered(lambda line: line.package_id == source_package)
                package_rows = allocations.filtered(lambda line: line.source_package_id == source_package)
                if set(package_rows.mapped('source_move_line_id').ids) != set(package_move_lines.ids) or any(line.handling_type != 'direct_outbound' or line.destination_package_id != source_package for line in package_rows):
                    raise UserError('A source pallet can be directly outbound only when all of its picked goods stay on that pallet.')
                package_quants = self.env['stock.quant'].sudo().search([('package_id', '=', source_package.id), ('location_id.usage', '=', 'internal'), ('quantity', '>', 0)])
                if any(quant.product_id.tracking == 'serial' and not quant.lot_id for quant in package_quants):
                    raise UserError('A source pallet with an untracked serial number cannot be directly outbound.')
                stock_quantities = defaultdict(float)
                demand_quantities = defaultdict(float)
                products = {}
                for quant in package_quants:
                    key = (quant.product_id.id, quant.lot_id.id if quant.lot_id else False)
                    stock_quantities[key] += quant.quantity
                    products[key] = quant.product_id
                for move_line in package_move_lines:
                    key = (move_line.product_id.id, move_line.lot_id.id if move_line.lot_id else False)
                    demand_quantities[key] += move_line.quantity
                    products[key] = move_line.product_id
                if set(stock_quantities) != set(demand_quantities):
                    raise UserError('A direct outbound source pallet must exactly match its picked goods.')
                for key, stock_quantity in stock_quantities.items():
                    if float_compare(stock_quantity, demand_quantities[key], precision_rounding=products[key].uom_id.rounding) != 0:
                        raise UserError('A direct outbound source pallet must exactly match its picked goods.')
            target_packages = allocations.filtered(lambda line: line.handling_type == 'palletize').mapped('destination_package_id')
            if target_packages:
                occupied_packages = self.env['stock.quant'].sudo().search([('package_id', 'in', target_packages.ids), ('location_id.usage', '=', 'internal'), ('quantity', '>', 0)]).mapped('package_id')
                if occupied_packages:
                    raise UserError('Destination pallets must be empty before palletization: %s.' % ', '.join(occupied_packages.mapped('display_name')))
            for move_line in move_lines:
                rows = allocations_by_move_line[move_line.id].sorted('id')
                first_row = rows[:1]
                move_line.write({'quantity': first_row.quantity, 'result_package_id': first_row.destination_package_id.id, 'outbound_palletization_id': rec.id, 'outbound_palletization_type': first_row.handling_type})
                for row in rows[1:]:
                    values = move_line.copy_data()[0]
                    values.update({'picking_id': move_line.picking_id.id, 'move_id': move_line.move_id.id, 'product_id': move_line.product_id.id, 'product_uom_id': move_line.product_uom_id.id, 'location_id': move_line.location_id.id, 'location_dest_id': move_line.location_dest_id.id, 'package_id': move_line.package_id.id, 'lot_id': move_line.lot_id.id, 'lot_name': move_line.lot_name, 'owner_id': move_line.owner_id.id, 'quantity': row.quantity, 'result_package_id': row.destination_package_id.id, 'outbound_palletization_id': rec.id, 'outbound_palletization_type': row.handling_type})
                    self.env['stock.move.line'].create(values)
            rec.write({'state': 'validated', 'validated_by_id': self.env.user.id, 'validated_at': fields.Datetime.now()})
        return True

    def action_reset_palletization(self):
        for rec in self:
            rec.lock_for_update()
            if rec.state not in ('pending', 'in_progress'):
                raise UserError('Only pending or in-progress palletization can be reset. Validated palletization cannot be reset.')
            rec.palletization_lines.with_context(vas_palletization_reset=True).unlink()
            rec.write({'state': 'pending', 'started_by_id': False, 'started_at': False, 'validated_by_id': False, 'validated_at': False})
        return True

    def action_cancel_palletization(self):
        for rec in self:
            if rec.state == 'cancelled':
                continue
            if rec.state == 'validated':
                raise UserError('Validated palletization cannot be cancelled.')
            rec.action_reset_palletization()
            rec.write({'state': 'cancelled'})
        return True

    def action_create_transport_pallets(self, pallet_count):
        package_model = self.env['stock.quant.package']
        packages = package_model
        for rec in self:
            rec.lock_for_update()
            if rec.state not in ('pending', 'in_progress'):
                raise UserError('Transport pallets can only be created before palletization is validated.')
            try:
                count = int(pallet_count)
            except (TypeError, ValueError):
                raise UserError('Enter a valid transport pallet quantity.')
            if count <= 0:
                raise UserError('Transport pallet quantity must be greater than zero.')
            document_number = rec.vas_order_id.source_document_number or rec.name
            transport_pallet_prefix = document_number if document_number.upper().startswith('OUT-') else 'OUT-%s' % document_number
            start_number = len(rec.transport_pallet_ids) + 1
            values_list = [{'name': '%s-P%03d' % (transport_pallet_prefix, number), 'reference': document_number, 'vas_outbound_palletization_id': rec.id} for number in range(start_number, start_number + count)]
            packages |= package_model.create(values_list)
        return packages

    def action_print_transport_pallet_labels(self):
        packages = self.env['stock.quant.package']
        for rec in self:
            if not rec.transport_pallet_ids:
                raise UserError('Create transport pallets before printing labels.')
            packages |= rec.transport_pallet_ids
        return self.env.ref('wd_warehouse_value_add.action_report_vas_transport_pallet_label').report_action(packages) if packages else False

    def get_scan_state(self):
        self.ensure_one()
        return {'id': self.id, 'name': self.name, 'state': self.state, 'vas_order_name': self.vas_order_id.display_name, 'picking_names': self.picking_ids.mapped('name'), 'line_count': len(self.palletization_lines)}


class VasOutboundPalletizationLine(models.Model):
    _name = 'wd.vas.outbound.palletization.line'
    _description = 'VAS Outbound Palletization Line'
    _order = 'id desc'

    palletization_id = fields.Many2one('wd.vas.outbound.palletization', string='Palletization', required=True, copy=False, ondelete='cascade', index=True)
    source_move_line_id = fields.Many2one('stock.move.line', string='Source Move Line', required=True, copy=False, ondelete='restrict', index=True)
    source_package_id = fields.Many2one('stock.quant.package', string='Source Pallet', readonly=True, copy=False, ondelete='restrict', index=True)
    product_id = fields.Many2one('product.product', string='Product', required=True, readonly=True, copy=False, ondelete='restrict', index=True)
    lot_id = fields.Many2one('stock.lot', string='Lot/Serial Number', readonly=True, copy=False, ondelete='restrict', index=True)
    quantity = fields.Float(string='Quantity', required=True, copy=False)
    destination_package_id = fields.Many2one('stock.quant.package', string='Destination Pallet', required=True, copy=False, ondelete='restrict', index=True)
    handling_type = fields.Selection([('palletize', 'Palletize'), ('direct_outbound', 'Direct Outbound')], string='Handling', required=True, copy=False, index=True)
    state = fields.Selection(related='palletization_id.state', string='Status', store=True, readonly=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        palletization_model = self.env['wd.vas.outbound.palletization']
        move_line_model = self.env['stock.move.line']
        palletization_ids = sorted({vals.get('palletization_id') for vals in vals_list if vals.get('palletization_id')})
        if palletization_ids:
            palletization_model.browse(palletization_ids).lock_for_update()
        for vals in vals_list:
            palletization_id = vals.get('palletization_id')
            source_move_line_id = vals.get('source_move_line_id')
            palletization = palletization_model.browse(palletization_id)
            source_move_line = move_line_model.browse(source_move_line_id)
            if not palletization or palletization.state not in ('pending', 'in_progress') or not source_move_line or source_move_line not in palletization.get_picking_move_lines():
                raise UserError('Choose a picked source line from this palletization.')
            if vals.get('quantity', 0.0) <= 0:
                raise UserError('Palletization quantity must be greater than zero.')
            if vals.get('handling_type') == 'direct_outbound' and vals.get('destination_package_id') != source_move_line.package_id.id:
                raise UserError('Direct outbound must keep the source pallet as destination.')
            if vals.get('handling_type') == 'palletize':
                destination_package_ids = self.env['stock.quant.package'].sudo().search([('id', '=', vals.get('destination_package_id')), ('vas_outbound_palletization_id', '=', palletization.id)], limit=1).ids
                if not destination_package_ids:
                    raise UserError('Palletized goods must use a transport pallet created for this palletization.')
            vals.update({'source_package_id': source_move_line.package_id.id, 'product_id': source_move_line.product_id.id, 'lot_id': source_move_line.lot_id.id})
            existing_quantity = sum(palletization.palletization_lines.filtered(lambda line: line.source_move_line_id == source_move_line).mapped('quantity'))
            rounding = source_move_line.product_uom_id.rounding or source_move_line.product_id.uom_id.rounding
            if float_compare(existing_quantity + vals['quantity'], source_move_line.quantity, precision_rounding=rounding) > 0:
                raise UserError('Palletization quantity exceeds the picked source quantity.')
        records = super().create(vals_list)
        for palletization in records.mapped('palletization_id'):
            if palletization.state == 'pending':
                palletization.write({'state': 'in_progress', 'started_by_id': self.env.user.id, 'started_at': fields.Datetime.now()})
        return records

    def write(self, vals):
        for rec in self:
            if rec.state not in ('pending', 'in_progress') and not self.env.context.get('vas_palletization_reset'):
                raise UserError('Validated palletization lines cannot be edited. Reset palletization first.')
            if 'source_move_line_id' in vals and vals['source_move_line_id'] != rec.source_move_line_id.id:
                raise UserError('Source move line cannot be changed after the palletization allocation is created.')
            quantity = vals.get('quantity', rec.quantity)
            destination_package_id = vals.get('destination_package_id', rec.destination_package_id.id)
            handling_type = vals.get('handling_type', rec.handling_type)
            if quantity <= 0:
                raise UserError('Palletization quantity must be greater than zero.')
            if handling_type == 'direct_outbound' and destination_package_id != rec.source_package_id.id:
                raise UserError('Direct outbound must keep the source pallet as destination.')
            if handling_type == 'palletize' and destination_package_id == rec.source_package_id.id:
                raise UserError('Palletized goods must use a different destination pallet.')
            if handling_type == 'palletize':
                destination_package_ids = self.env['stock.quant.package'].sudo().search([('id', '=', destination_package_id), ('vas_outbound_palletization_id', '=', rec.palletization_id.id)], limit=1).ids
                if not destination_package_ids:
                    raise UserError('Palletized goods must use a transport pallet created for this palletization.')
            allocated_quantity = sum((rec.palletization_id.palletization_lines - rec).filtered(lambda line: line.source_move_line_id == rec.source_move_line_id).mapped('quantity'))
            rounding = rec.source_move_line_id.product_uom_id.rounding or rec.source_move_line_id.product_id.uom_id.rounding
            if float_compare(allocated_quantity + quantity, rec.source_move_line_id.quantity, precision_rounding=rounding) > 0:
                raise UserError('Palletization quantity exceeds the picked source quantity.')
        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec.state not in ('pending', 'in_progress') and not self.env.context.get('vas_palletization_reset'):
                raise UserError('Validated palletization lines cannot be deleted. Reset palletization first.')
        return super().unlink()


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    outbound_palletization_id = fields.Many2one('wd.vas.outbound.palletization', string='Outbound Palletization', readonly=True, copy=False, ondelete='set null', index=True)
    outbound_palletization_type = fields.Selection([('palletize', 'Palletize'), ('direct_outbound', 'Direct Outbound')], string='Outbound Palletization Handling', readonly=True, copy=False, index=True)


class StockQuantPackage(models.Model):
    _inherit = 'stock.quant.package'

    vas_outbound_palletization_id = fields.Many2one('wd.vas.outbound.palletization', string='VAS Outbound Palletization', readonly=True, copy=False, ondelete='set null', index=True)
