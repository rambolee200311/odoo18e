from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import float_is_zero, float_compare
import logging

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    def action_force_validate(self):
        """Force validate picking while ignoring valuation checks and push rules.
        
        Returns:
            bool: True if validation was successful
        """
        self._check_quantity()
        for picking in self:
            try:
                _logger.info("Starting forced validation for picking: %s (ID: %s)", picking.name, picking.id)
                
                # Ensure all moves are in the correct state first
                picking.move_ids.filtered(lambda m: m.state == 'draft')._action_confirm()
                picking.move_ids.filtered(lambda m: m.state == 'confirmed')._action_assign()
                
                # Ensure all moves have a group_id to avoid valuation issues
                if not picking.group_id:
                    group = self.env["procurement.group"].create({
                        'name': picking.name,
                    })
                    picking.move_ids.write({'group_id': group.id})
                    picking.write({'group_id': group.id})
                else:
                    picking.move_ids.write({'group_id': picking.group_id.id})
                
                # Create comprehensive context to bypass all checks
                force_context = {
                    'skip_valuation': True,
                    'skip_stock_checks': True,
                    'skip_quantity_check': True,
                    #'skip_push_rules': True,
                    'force_validate': True,
                    'cancel_backorder': True
                }
                
                # Force validate all moves first
                self._force_validate_stock_moves(picking.move_ids.ids)
                
                # Now validate the picking using the standard method with force context
                result = picking.with_context(**force_context).button_validate()
                
                # Verify that picking and moves are properly done
                if picking.state != 'done':
                    picking.write({'state': 'done'})
                
                _logger.info("Picking %s forced validation successful", picking.name)
                return result
                
            except Exception as e:
                _logger.error("Picking %s forced validation failed: %s", picking.name, str(e))
                # Don't rollback immediately, try alternative approach
                return self._alternative_force_validate(picking)
    
    def _force_validate_stock_moves(self, move_ids):
        """
        Force validate stock moves with comprehensive error handling
        
        Args:
            move_ids (list): List of stock move IDs to validate
            
        Returns:
            bool: True if all moves were validated successfully
        """
        moves = self.env['stock.move'].browse(move_ids)
        
        # Process moves by state
        for move in moves:
            try:
                # Skip all checks and force validation - this will properly update quants
                move.with_context(
                    skip_quantity_check=True,
                    skip_backorder=True,
                    cancel_backorder=True,
                    skip_valuation=True,
                    force_validate=True
                )._action_done()
                
                _logger.info("Move %s force validated successfully", move.id)
                
            except Exception as e:
                _logger.warning("Force validation of move %s failed: %s", move.id, str(e))
                raise UserError(_("Could not force validate move %s: %s") % (move.name, str(e)))
        
        return True
    
    def _alternative_force_validate(self, picking):
        """
        Alternative approach when primary method fails
        """
        try:
            _logger.info("Trying alternative force validation for picking %s", picking.name)
            
            # Try validating moves individually with more aggressive context
            for move in picking.move_ids:
                # Ensure move is in assign state
                if move.state != 'assigned':
                    move._action_assign()
                
                # Force the move to done state through the proper method
                move.with_context(
                    skip_quantity_check=True,
                    skip_valuation=True,
                    force_validate=True,
                    disable_security_checks=True
                )._action_done()
            
            # Update picking state
            picking.write({'state': 'done'})
            
            _logger.info("Alternative force validation successful for picking %s", picking.name)
            return True
            
        except Exception as e:
            _logger.error("Alternative force validation also failed for picking %s: %s", picking.name, str(e))
            raise UserError(_("Force validation failed for picking %s: %s") % (picking.name, str(e)))
    
    def action_force_validate_simple(self):
        """
        Simplified force validation - just validate moves then picking
        """
        for picking in self:
            try:
                # Validate all moves
                for move in picking.move_ids:
                    if move.state != 'done':
                        move._action_done()
                
                # Validate picking
                return picking.button_validate()
                
            except Exception as e:
                _logger.error("Simple force validation failed for picking %s: %s", picking.name, str(e))
                raise UserError(_("Simple validation failed: %s") % str(e))