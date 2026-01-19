from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import float_is_zero, float_compare
import logging

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    # COMPLETE REVERSE VALIDATION LOGIC
    def button_reverse_validate(self):    
        """Comprehensive reverse validation with complete stock recovery"""
        for picking in self:
            # Server-side permission check
            if not (self.env.user.has_group('stock.group_stock_manager') or
                    self.env.user.has_group('base.group_system')):
                raise UserError(_("You are not allowed to perform a reverse validation. Contact your administrator."))
            if picking.state != 'done':
                raise UserError(_("You can only reverse validate transfers that are in 'Done' state."))
            
            # If this is an internal transfer, look for outgoing deliveries to remove
            try:
                if picking.picking_type_id and getattr(picking.picking_type_id, 'code', '') == 'internal':
                    Delivery = self.env['stock.picking'].sudo()
                    deliveries = Delivery.search([
                        ('origin', '=', picking.name),
                        ('picking_type_id.code', '=', 'outgoing'),
                    ])
                    if deliveries:
                        removed = []
                        for d in deliveries:
                            if d.state == 'done':
                                raise UserError(_("Cannot automatically remove dependent delivery %s because it is in 'done' state. Please reverse or cancel it first.") % d.display_name)
                            
                            d_display = d.display_name
                            try:
                                d.unlink()
                                removed.append(d_display)
                            except Exception:
                                try:
                                    d.action_cancel()
                                except Exception:
                                    pass
                                try:
                                    d.unlink()
                                    removed.append(d_display)
                                except Exception as e:
                                    raise UserError(_("Failed to remove dependent delivery %s: %s") % (d_display, e))
                        if removed:
                            picking.message_post(body=_("Automatically removed dependent deliveries: %s") % (', '.join(removed)))
            except UserError:
                raise
            except Exception:
                picking.message_post(body=_("Warning: could not automatically remove related deliveries for %s") % (picking.display_name,))
            
            # Verify no downstream moves exist
            downstream_moves = picking.move_ids.move_dest_ids.filtered(lambda m: m.state != 'cancel')
            downstream_moves = downstream_moves.filtered(lambda m: m.picking_id and m.picking_id.exists())
            if downstream_moves:
                downstream_picking_ids = list(set(downstream_moves.mapped('picking_id.id')))
                downstream_picking_names = self.env['stock.picking'].browse(downstream_picking_ids).mapped('name')
                raise UserError(_(
                    "Cannot reverse validate: There are downstream moves (%s) that depend on this transfer. "
                    "Please cancel them first."
                ) % ', '.join(downstream_picking_names))
            
            with self.env.cr.savepoint():
                try:
                    # Store all quant modifications for potential rollback
                    quant_modifications = []
                    
                    # Select only the moves that were actually done and need reversal
                    moves_to_reverse = picking.move_ids.filtered(lambda m: m.state == 'done' and m.quantity > 0)
                    for move in moves_to_reverse:
                        for move_line in move.move_line_ids:
                            # Reverse the quant impact for this move line
                            picking._reverse_quant_impact(move_line, quant_modifications)

                            # Reverse lot location if applicable
                            picking._reverse_lot_location(move_line)

                    # Update only the moves we processed (avoid touching cancelled moves)
                    if moves_to_reverse:
                        moves_to_reverse.write({
                            'state': 'draft',
                            'quantity': 0,
                        })
                    
                    # Update picking state
                    picking.write({
                        'state': 'draft',
                        'date_done': False,
                    })
                    
                    # Recompute relevant computed fields on locations after manual quant changes.
                    locations_to_recompute = (picking.move_ids.mapped('location_id') |
                                            picking.move_ids.mapped('location_dest_id'))
                    if locations_to_recompute:
                        locs = self.env['stock.location'].browse(locations_to_recompute.ids)
                        try:
                            locs._compute_weight()
                        except Exception:
                            pass
                        try:
                            locs._compute_is_empty()
                        except Exception:
                            pass
                        try:
                            locs._compute_warehouse_id()
                        except Exception:
                            pass
                        
                        picking.message_post(
                            body=_("""
                            Complete reverse validation performed successfully.
                            Stock recovery details:
                            - Quantities restored in %s locations
                            - %s lot allocations recovered
                            - All inventory impacts reversed
                            """) % (len(locations_to_recompute), 
                                len(picking.move_ids.mapped('move_line_ids.lot_id')))
                        )
                except Exception as e:
                    # Rollback quant modifications on error
                    picking._rollback_quant_modifications(quant_modifications)
                    raise UserError(_("Reverse validation failed: %s") % str(e))
                
                return True
    
    def _reverse_quant_impact(self, move_line, quant_modifications):
        """Reverse the quant impact for a specific move line"""
        product = move_line.product_id
        quantity = move_line.quantity
        
        # Handle destination location (remove quantity)
        dest_domain = [
            ('product_id', '=', product.id),
            ('location_id', '=', move_line.location_dest_id.id),
        ]
        if move_line.lot_id:
            dest_domain.append(('lot_id', '=', move_line.lot_id.id))
        if move_line.owner_id:
            dest_domain.append(('owner_id', '=', move_line.owner_id.id))
        
        dest_quants = self.env['stock.quant'].search(dest_domain)
        remaining_qty = quantity

        # Compute total available in destination to avoid creating negative quants
        dest_total = sum(dest_quants.mapped('quantity'))
        if dest_total < quantity:
            # Fail early: do not create negative quants — require manual intervention or stock correction
            raise UserError(_(
                "Cannot reverse move line for product %s: destination location %s only has %s units available but %s are required to reverse.")
                % (product.display_name, move_line.location_dest_id.display_name, dest_total, quantity))

        for dest_quant in dest_quants:
            if remaining_qty <= 0:
                break

            qty_to_remove = min(remaining_qty, dest_quant.quantity)
            if qty_to_remove > 0:
                quant_modifications.append(('decrement', dest_quant.id, qty_to_remove))
                # Use write for safety so ORM triggers any necessary constraints
                dest_quant.write({'quantity': float(dest_quant.quantity) - float(qty_to_remove)})
                remaining_qty -= qty_to_remove
        
        # Handle source location (restore quantity)
        source_domain = [
            ('product_id', '=', product.id),
            ('location_id', '=', move_line.location_id.id),
        ]
        if move_line.lot_id:
            source_domain.append(('lot_id', '=', move_line.lot_id.id))
        if move_line.owner_id:
            source_domain.append(('owner_id', '=', move_line.owner_id.id))
        
        source_quants = self.env['stock.quant'].search(source_domain)
        
        if source_quants:
            quant_modifications.append(('increment', source_quants[0].id, quantity))
            source_quants[0].write({'quantity': float(source_quants[0].quantity) + float(quantity)})
        else:
            # Create new quant in source location
            created = self.env['stock.quant'].create({
                'product_id': product.id,
                'location_id': move_line.location_id.id,
                'quantity': quantity,
                'lot_id': move_line.lot_id.id,
                'owner_id': move_line.owner_id.id,
            })
            # Track created quant so rollback helper can remove it if needed
            quant_modifications.append(('create', created.id, quantity))


    def _reverse_lot_location(self, move_line):
        """Reverse the lot location if the lot was moved"""
        if move_line.lot_id:
            # Find the quant for this lot and restore its location
            lot_quant = self.env['stock.quant'].search([
                ('lot_id', '=', move_line.lot_id.id),
                ('product_id', '=', move_line.product_id.id),
                ('quantity', '>', 0)
            ], order='id desc', limit=1)
            
            if lot_quant and lot_quant.location_id == move_line.location_dest_id:
                # Move the lot back to source location
                lot_quant.location_id = move_line.location_id

    def _rollback_quant_modifications(self, modifications):
        """Rollback quant modifications in case of error"""
        for operation, quant_id, quantity in modifications:
            quant = self.env['stock.quant'].browse(quant_id)
            if quant.exists():
                if operation == 'decrement':
                    quant.quantity += quantity
                elif operation == 'increment':
                    quant.quantity -= quantity
                elif operation == 'create':
                    # Remove the created quant
                    quant.unlink()

        # Do not call button_validate or perform other operations here.
        # Rollback should only revert quant changes to restore previous stock state.
        return True

    def delete_done_pickings(self):
        """Prompt user for confirmation before deleting done pickings"""
        action = {
            'type': 'ir.actions.act_window',
            'name': 'Confirm Deletion',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_message': 'Are you sure you want to delete all done pickings?',
                'default_confirm_action': 'delete_done_pickings_confirm',
            },
        }
        return action

    def delete_done_pickings_confirm(self):
        """Delete pickings in 'done' state after resetting their state and cleaning related records."""
        done_pickings = self.search([('state', '=', 'done')])
        for picking in done_pickings:
            # Reset state of stock moves and move lines
            for move in picking.move_ids:
                move.state = 'draft'
            for move_line in picking.move_line_ids:
                move_line.state = 'draft'
            # Skip deletion of quants due to access restrictions
            # You can log or handle quants differently if needed
            # Handle related quants
            # for move_line in picking.move_line_ids:
            #    quants = self.env['stock.quant'].search([('lot_id', '=', move_line.lot_id.id)])
            #    quants.unlink()  # Delete related quants

            # Forcefully reset picking state to 'draft'
            picking.state = 'draft'

            # Unlink the picking
            picking.unlink()