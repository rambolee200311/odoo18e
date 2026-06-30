from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class StockMove(models.Model):
    _inherit = 'stock.move'

    original_location_id = fields.Many2one('stock.location', copy=False)
    original_location_dest_id = fields.Many2one('stock.location', copy=False)
    inbound_order_product_pallet_id = fields.Integer('Inbound Order Product Pallet ID')
    nine_digit_linglong_code = fields.Char(
        string="Nine Digit Linglong Code",
        related='product_id.nine_digit_linglong_code',
        store=True
    )
    outbound_order_product_id = fields.Integer('Outbound Order ProductID')

    def write(self, vals):
        """Write override that prevents changing location fields for processed moves.

        - If `validation_in_progress` is set in the context, defer to super().
        - When `location_id`/`location_dest_id` are present in `vals`, perform
          a per-record write: for records already in state 'done' we silently
          ignore those location keys (log a debug); for other records we apply
          the full `vals`.

        This avoids Odoo's stock valuation ValidationError which is raised when
        location/valuation-related fields are changed after processing.
        """
        if self.env.context.get('validation_in_progress'):
            return super().write(vals)

        # If no location-related fields are in vals, write normally
        location_keys = {'location_id', 'location_dest_id'}
        if not any(k in vals for k in location_keys):
            return super().write(vals)

        # Per-record handling: skip location keys for done moves
        result = True
        for move in self:
            # Build vals for this single record
            if move.state == 'done':
                # Don't change locations for processed moves — drop those keys
                filtered_vals = {k: v for k, v in vals.items() if k not in location_keys}
                if filtered_vals:
                    # apply remaining non-location changes
                    try:
                        res = super(StockMove, move).write(filtered_vals)
                    except ValidationError as e:
                        if self.env.context.get('ignore_valuation_check'):
                            _logger.warning('Ignored valuation ValidationError while writing move %s: %s', move.id, e)
                            res = True
                        else:
                            raise
                    result = result and res
                else:
                    # Nothing to write (all keys were location fields)
                    _logger.debug('Skipping location change on done move %s', move.id)
                    result = result and True
            else:
                try:
                    res = super(StockMove, move).write(vals)
                except ValidationError as e:
                    if self.env.context.get('ignore_valuation_check'):
                        _logger.warning('Ignored valuation ValidationError while writing move %s: %s', move.id, e)
                        res = True
                    else:
                        raise
                result = result and res

        return result

    def _should_disable_merge(self):
        """ONE PICK = ONE DELIVERY - Check if move should not be merged"""
        self.ensure_one()
        return (self.picking_type_id.code == 'outgoing' and 
                self.move_orig_ids and 
                any(orig.picking_type_id.code == 'internal' for orig in self.move_orig_ids))

    def _action_confirm(self, merge=True, merge_into=False):
        """Override confirmation to prevent merging"""
        moves_no_merge = self.filtered(lambda m: m._should_disable_merge())
        moves_can_merge = self - moves_no_merge
        
        result = self.env['stock.move']
        
        # Process moves that should not be merged
        if moves_no_merge:
            moves_by_origin = {}
            for move in moves_no_merge:
                origin = move._get_internal_origin_picking()
                origin_key = origin.id if origin else 'external'
                moves_by_origin.setdefault(origin_key, self.env['stock.move'])
                moves_by_origin[origin_key] |= move
            
            for origin_moves in moves_by_origin.values():
                origin_moves.write({'group_id': False})
                confirmed = super(StockMove, origin_moves)._action_confirm(merge=False)
                result |= confirmed
        
        # Process moves that can be merged normally
        if moves_can_merge:
            confirmed = super(StockMove, moves_can_merge)._action_confirm(merge=merge)
            result |= confirmed
        
        return result

    def _get_internal_origin_picking(self):
        """Get the internal transfer that originated this move"""
        self.ensure_one()
        internal_moves = self.move_orig_ids.filtered(
            lambda m: m.picking_type_id.code == 'internal'
        )
        return internal_moves.picking_id if internal_moves else None

    def _assign_picking(self):
        """Assign picking while maintaining ONE PICK = ONE DELIVERY rule"""
        special_moves = self.filtered(lambda m: m._should_disable_merge())
        normal_moves = self - special_moves
        
        # Process normal moves first
        if normal_moves:
            super(StockMove, normal_moves)._assign_picking()
        
        # Process special moves with origin grouping
        if special_moves:
            moves_by_origin = {}
            for move in special_moves:
                origin = move._get_internal_origin_picking()
                origin_key = origin.id if origin else 'external'
                moves_by_origin.setdefault(origin_key, self.env['stock.move'])
                moves_by_origin[origin_key] |= move
            
            # Assign each origin group to separate pickings
            for origin_moves in moves_by_origin.values():
                picking = self._get_origin_picking(origin_moves)
                origin_moves.write({'picking_id': picking.id})
        
        return True

    def _get_origin_picking(self, moves):
        """Find or create picking for moves from same internal origin"""
        if not moves:
            return False
        
        origin = moves[0]._get_internal_origin_picking()
        
        # CORRECT: Delivery location = Internal transfer's destination
        if origin and origin.picking_type_id.code == 'internal':
            delivery_location_id = origin.location_dest_id.id
        else:
            delivery_location_id = moves[0].location_id.id
        
        # Find existing picking
        domain = [
            ('picking_type_id', '=', moves[0].picking_type_id.id),
            ('location_id', '=', delivery_location_id),
            ('location_dest_id', '=', moves[0].location_dest_id.id),
            ('state', 'in', ['draft', 'confirmed', 'assigned']),
        ]
        
        if origin:
            domain.append(('origin', '=', origin.name))
        
        existing = self.env['stock.picking'].search(domain, limit=1)
        if existing:
            return existing
        
        # Create new picking for this origin group
        picking_vals = {
            'picking_type_id': moves[0].picking_type_id.id,
            'location_id': delivery_location_id,
            'location_dest_id': moves[0].location_dest_id.id,
            'origin': origin.name if origin else moves[0].origin or '',
            'group_id': False,
        }
        
        if moves[0].partner_id:
            picking_vals['partner_id'] = moves[0].partner_id.id
        
        return self.env['stock.picking'].create(picking_vals)

    def _action_assign(self):
        """Ensure move lines are created during assignment"""
        result = super()._action_assign()
        
        # Create missing move lines
        moves_without_lines = self.filtered(
            lambda m: m.state == 'assigned' and not m.move_line_ids
        )
        
        for move in moves_without_lines:
            move._create_move_line()
        
        return result

    def _create_move_line(self):
        """Create move line if missing"""
        self.ensure_one()
        if self.state in ['confirmed', 'assigned'] and not self.move_line_ids:
            self.env['stock.move.line'].create({
                'move_id': self.id,
                'product_id': self.product_id.id,
                'product_uom_id': self.product_uom.id,
                'location_id': self.location_id.id,
                'location_dest_id': self.location_dest_id.id,
                'quantity': self.quantity,
                'quantity_product_uom': self.quantity_product_uom,
                'qty_done': 0.0,
            })

    def _action_done(self, cancel_backorder=False):
        """Store original locations before completion"""
        for move in self:
            if not move.original_location_id:
                move.original_location_id = move.location_id.id
            if not move.original_location_dest_id:
                move.original_location_dest_id = move.location_dest_id.id
        
        return super()._action_done(cancel_backorder=cancel_backorder)