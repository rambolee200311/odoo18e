from odoo import models, fields, api, _
from odoo.exceptions import UserError

class TransferOrderCreatePicking(models.Model):
    _inherit = 'world.depot.transfer.order'

    def action_create_stock_picking(self):
        """
        Create a stock picking for the transfer order using pick type default locations
        """
        for record in self:
            # Pre-condition validation
            if record.state != 'confirm':
                raise UserError(_('Transfer order must be confirmed before creating a stock picking.'))
            if not record.pick_type:
                raise UserError(_('Picking type must be set before creating a stock picking.'))
            if not record.t_date:
                raise UserError(_('Transfer date must be set before creating a stock picking.'))
            if not record.line_ids:
                raise UserError(_('Transfer order must have at least one product line.'))
            
            # Check if stock picking already exists
            if record.stock_picking_id:
                raise UserError(_('A stock picking already exists for this Transfer Order.'))
            
            # Find or create procurement group
            group = self.env['procurement.group'].search([('name', '=', record.billno)], limit=1)
            if not group:
                group = self.env['procurement.group'].create({'name': record.billno})
            
            # Create the stock picking
            picking_vals = {
                'picking_type_id': record.pick_type.id,
                'location_id': record.pick_type.default_location_src_id.id,
                'location_dest_id': record.pick_type.default_location_dest_id.id,
                'origin': record.billno,
                'scheduled_date': record.t_date,
                'transfer_order_id': record.id,
                'group_id': group.id,
                'partner_id': record.owner.id if record.owner else False,
            }
            picking = self.env['stock.picking'].create(picking_vals)
            
            # Create stock moves for each product line
            for line in record.line_ids:
                # Create stock move
                stock_move = self.env['stock.move'].create({
                    'name': line.product.name,
                    'product_id': line.product.id,
                    'product_uom_qty': line.quantity,
                    'product_uom': line.product.uom_id.id,
                    'picking_id': picking.id,
                    'location_id': picking.location_id.id,  # Use picking's source location
                    'location_dest_id': picking.location_dest_id.id,  # Use picking's destination location
                    'transfer_order_line_id': line.id,
                    'group_id': group.id,
                })
                
                # Validate stock move was created successfully
                if not stock_move.exists():
                    raise UserError(_('Failed to create stock move for product %s.') % line.product.name)
            
            # Update the transfer order with the picking reference
            record.stock_picking_id = picking.id
            
            # Return success message
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Stock Picking Created'),
                    'message': _('Stock picking %s has been created successfully.') % picking.name,
                    'sticky': False,
                }
            }
    