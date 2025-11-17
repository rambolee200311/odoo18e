from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import float_is_zero, float_compare


class StockRoute(models.Model):
    _inherit = 'stock.route'
    
    disable_auto_merge = fields.Boolean(
        string='Disable Auto Merge',
        help='If checked, transfers using this route will not be automatically merged'
    )


class StockRule(models.Model):
    _inherit = 'stock.rule'

    disable_auto_merge = fields.Boolean(
        string='Disable Auto Merge',
        related='route_id.disable_auto_merge',
        store=True,
        help='If checked, transfers using this rule will not be automatically merged'
    )


class StockLot(models.Model):
    _inherit = 'stock.lot'

    bill_of_lading = fields.Char('Bill of Lading')
    cntrno = fields.Char('Container Number')


class StockLocation(models.Model):
    _inherit = 'stock.location'

    def _get_removal_strategy_order(self, removal_strategy):
        if removal_strategy == 'fifo':
            return 'date, id'
        return super(StockLocation, self)._get_removal_strategy_order(removal_strategy)


class StockMove(models.Model):
    _inherit = 'stock.move'

    # InboundOrderProductsOfPallet's ID
    inbound_order_product_pallet_id = fields.Integer('Inbound Order Product Pallet ID')
    nine_digit_linglong_code = fields.Char(
        string="Nine Digit Linglong Code",
        related='product_id.nine_digit_linglong_code',
        store=True
    )
    outbound_order_product_id = fields.Integer('Outbound Order ProductID')
    
    def _has_disable_auto_merge(self):
        """Return True if this move should avoid auto-merge based on route/rule settings"""
        # Check explicit route on move
        if self.route_ids and any(route.disable_auto_merge for route in self.route_ids):
            return True
        
        # Check rule's route setting
        if self.rule_id and self.rule_id.route_id and self.rule_id.route_id.disable_auto_merge:
            return True
            
        # Check if originating from internal transfer with disabled merge routes
        if self.move_orig_ids:
            for orig_move in self.move_orig_ids:
                if (orig_move.picking_id and 
                    orig_move.picking_type_id.code == 'internal' and
                    any(move._has_disable_auto_merge() for move in orig_move.picking_id.move_ids)):
                    return True
                    
        return False

    def _prepare_merge_moves_distinct_fields(self):
        distinct_fields = super()._prepare_merge_moves_distinct_fields()
        distinct_fields.append('inbound_order_product_pallet_id')
        distinct_fields.append('outbound_order_product_id') 
        distinct_fields.append('route_ids')
        
        # Critical: Always include these fields when auto-merge is disabled
        if any(m._has_disable_auto_merge() for m in self):
            distinct_fields.extend(['origin', 'picking_id', 'group_id', 'rule_id'])
            
        return distinct_fields
    
    def _action_confirm(self, merge=True, merge_into=False):
        """COMPLETELY OVERRIDE - Prevent any merging for moves with disabled auto-merge"""
        # Separate moves into two groups
        moves_no_merge = self.filtered(lambda m: m._should_completely_disable_merge())
        moves_can_merge = self - moves_no_merge
        
        result = self.env['stock.move']
        
        # Process moves that should NEVER be merged
        if moves_no_merge:
            # Process each move individually to ensure complete isolation
            for move in moves_no_merge:
                # Ensure move has no group_id before confirmation
                if move.group_id:
                    move.write({'group_id': False})
                result |= super(StockMove, move)._action_confirm(merge=False, merge_into=False)
        
        # Process moves that can be merged normally
        if moves_can_merge:
            result |= super(StockMove, moves_can_merge)._action_confirm(merge=merge, merge_into=merge_into)
        
        return result

    def _should_completely_disable_merge(self):
        """More comprehensive check for complete merge disabling"""
        if self._has_disable_auto_merge():
            return True
            
        # Internal transfers should never merge their outgoing moves
        if (self.picking_type_id.code == 'outgoing' and 
            self.move_orig_ids and 
            any(orig.picking_type_id.code == 'internal' for orig in self.move_orig_ids)):
            return True
            
        return False

    def _assign_picking(self):
        """COMPLETELY OVERRIDDEN - Strict assignment logic to prevent merging"""
        # First separate moves by their merge requirements
        moves_no_merge = self.filtered(lambda m: m._should_completely_disable_merge())
        moves_can_merge = self - moves_no_merge
        
        # Process moves that can merge normally first
        if moves_can_merge:
            super(StockMove, moves_can_merge)._assign_picking()
        
        # Process moves that should not merge with strict isolation
        for move in moves_no_merge:
            if move.state in ('cancel', 'done'):
                continue
                
            # Completely isolated assignment
            self._assign_picking_strict_isolation(move)
        
        return True

    def _assign_picking_strict_isolation(self, move):
        """Assign picking with absolute isolation - no merging possible"""
        # Remove any existing group_id
        if move.group_id:
            move.write({'group_id': False})
        
        # Look for completely empty picking with same characteristics
        domain = [
            ('picking_type_id', '=', move.picking_type_id.id),
            ('location_id', '=', move.location_id.id),
            ('location_dest_id', '=', move.location_dest_id.id),
            ('state', 'in', ['draft', 'confirmed']),
            ('group_id', '=', False),
            ('move_ids', '=', False),  # Must be completely empty
        ]
        
        # Additional domain for specific cases
        if move.partner_id:
            domain.append(('partner_id', '=', move.partner_id.id))
        
        picking = self.env['stock.picking'].search(domain, limit=1)
        
        if not picking:
            # Create completely new isolated picking
            picking_vals = {
                'picking_type_id': move.picking_type_id.id,
                'location_id': move.location_id.id,
                'location_dest_id': move.location_dest_id.id,
                'group_id': False,
                'origin': move.origin or '',
            }
            
            if move.partner_id:
                picking_vals['partner_id'] = move.partner_id.id
                
            picking = self.env['stock.picking'].create(picking_vals)
        
        # Assign move to this picking
        move.write({'picking_id': picking.id, 'group_id': False})
        
        return True

    def _check_assign_picking(self):
        """Override assignment check with strict isolation"""
        if self._should_completely_disable_merge():
            return self._assign_picking_strict_isolation(self)
        return super(StockMove, self)._check_assign_picking()

    def _get_new_picking_values(self):
        """Override to ensure new pickings don't get group_id"""
        values = super(StockMove, self)._get_new_picking_values()
        if self._should_completely_disable_merge():
            values['group_id'] = False
        return values

    def _merge_moves(self, merge_into=False):
        """COMPLETELY PREVENT merging for specific moves"""
        if any(move._should_completely_disable_merge() for move in self):
            # Return moves as-is without any merging
            return self
            
        return super(StockMove, self)._merge_moves(merge_into=merge_into)

    def _update_candidate_moves_list(self, candidate_moves_list):
        """Override to filter out moves that should not be merged"""
        if self._should_completely_disable_merge():
            # Return empty list to prevent this move from being considered for merging
            return []
            
        return super(StockMove, self)._update_candidate_moves_list(candidate_moves_list)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    bill_of_lading = fields.Char('Bill of Lading')
    cntrno = fields.Char('Container Number')
    ref_1 = fields.Char('Reference 1', help='Additional reference field for custom use')
    ref_2 = fields.Char('Reference 2', help='Additional reference field for custom use')
    planning_date = fields.Datetime('Planning Date', help='Date when the picking is planned to be processed')
    inbound_order_id = fields.Many2one(
        comodel_name='world.depot.inbound.order',
        string='Inbound Order',
        help='Reference to the related Inbound Order',
        readonly=True
    )
    outbound_order_id = fields.Many2one(
        comodel_name='world.depot.outbound.order',
        string='Outbound Order',
        help='Reference to the related Outbound Order',
        readonly=True
    )
    load_ref = fields.Char(string='Loading Reference', required=False, help='Reference for the Delivery')

    def _has_disable_auto_merge_routes(self):
        """Check if picking contains moves with disabled auto-merge"""
        return any(move._has_disable_auto_merge() for move in self.move_ids)

    @api.model
    def _check_grouping_compatibility(self, picking, move):
        """STRICT grouping compatibility check"""
        if not super(StockPicking, self)._check_grouping_compatibility(picking, move):
            return False
        
        # CRITICAL: Never group if either has disabled auto-merge
        if picking._has_disable_auto_merge_routes() or move._has_disable_auto_merge():
            return False
            
        # Additional strict checks for internal transfers
        if picking.move_ids and move.move_orig_ids:
            picking_internal_origins = set()
            for picking_move in picking.move_ids:
                if picking_move.move_orig_ids:
                    for orig_move in picking_move.move_orig_ids:
                        if orig_move.picking_id and orig_move.picking_type_id.code == 'internal':
                            picking_internal_origins.add(orig_move.picking_id.id)
            
            move_internal_origins = set()
            if move.move_orig_ids:
                for orig_move in move.move_orig_ids:
                    if orig_move.picking_id and orig_move.picking_type_id.code == 'internal':
                        move_internal_origins.add(orig_move.picking_id.id)
            
            if picking_internal_origins and move_internal_origins and picking_internal_origins != move_internal_origins:
                return False
        
        return True

    def action_assign(self):
        """Override with post-assignment separation check"""
        result = super(StockPicking, self).action_assign()
        
        # Post-assignment: ensure strict separation
        self._ensure_absolute_separation()
        
        return result

    def _ensure_absolute_separation(self):
        """Ensure complete separation of moves with disabled auto-merge"""
        for picking in self:
            # Check if this picking contains mixed moves (should be separated vs can be merged)
            moves_no_merge = picking.move_ids.filtered(lambda m: m._should_completely_disable_merge())
            moves_can_merge = picking.move_ids - moves_no_merge
            
            # If we have mixed moves, separate them
            if moves_no_merge and moves_can_merge:
                self._separate_mixed_picking(picking, moves_no_merge, moves_can_merge)

    def _separate_mixed_picking(self, picking, moves_no_merge, moves_can_merge):
        """Separate mixed picking into isolated pickings"""
        # Create new picking for moves that should not merge
        new_picking_vals = {
            'move_ids': [],
            'move_line_ids': [],
            'backorder_id': False,
            'origin': picking.origin,
            'picking_type_id': picking.picking_type_id.id,
            'location_id': picking.location_id.id,
            'location_dest_id': picking.location_dest_id.id,
            'partner_id': picking.partner_id.id,
            'scheduled_date': picking.scheduled_date,
            'group_id': False,  # Critical: no group_id
        }
        
        new_picking = picking.copy(new_picking_vals)
        
        # Move no-merge moves to new picking
        moves_no_merge.write({'picking_id': new_picking.id})
        if moves_no_merge.move_line_ids:
            moves_no_merge.move_line_ids.write({'picking_id': new_picking.id})

    def button_validate(self):
        """Final validation with separation check"""
        # Pre-validation separation check
        self._pre_validate_separation()
        
        # Perform standard validation checks
        for picking in self:
            if picking.picking_type_id.strict_quantity_control:
                for move in picking.move_ids:
                    if move.state in ('done', 'cancel'):
                        continue
                        
                    if float_compare(float(move.quantity or 0.0), move.product_uom_qty,
                                     precision_rounding=move.product_uom.rounding) != 0:
                        raise UserError(_(
                            "Recorded move quantity must equal demand quantity for product %s.\n"
                            "Demand: %s %s, Recorded move.quantity: %s %s\n\n"
                            "This is enforced by the operation type: %s"
                        ) % (move.product_id.display_name, move.product_uom_qty,
                            move.product_uom.name, move.quantity, move.product_uom.name,
                            picking.picking_type_id.name))

                    relevant_lines = move.move_line_ids.filtered(lambda ml: ml.state != 'cancel') # and float(ml.quantity or 0.0) >= 0.0)
                    if relevant_lines:
                        done_qty = sum(
                            ml.product_uom_id._compute_quantity(ml.quantity, move.product_uom)
                            for ml in relevant_lines
                        )
                        if float_compare(done_qty, move.product_uom_qty,
                                        precision_rounding=move.product_uom.rounding) != 0:
                            raise UserError(_(
                                "Actual done quantity (from move lines) must equal demand quantity for product %s.\n"
                                "Demand: %s %s, Actual done: %s %s\n\n"
                                "This is enforced by the operation type: %s"
                            ) % (move.product_id.display_name, move.product_uom_qty,
                                move.product_uom.name, done_qty, move.product_uom.name,
                                picking.picking_type_id.name))
        
        # Call original validation
        res = super(StockPicking, self).button_validate()
        
        # Post-validation processing
        for picking in self:
            # Propagate Bill of Lading / Container info to lots
            for move_line in picking.move_line_ids:
                if move_line.lot_id and not (move_line.lot_id.bill_of_lading or move_line.lot_id.cntrno):
                    move_line.lot_id.write({
                        'bill_of_lading': picking.bill_of_lading,
                        'cntrno': picking.cntrno,
                    })

            # Update inbound orders
            if getattr(picking.picking_type_id, 'code', '') == 'incoming' and picking.inbound_order_id:
                picking.inbound_order_id.write({
                    'i_date': picking.date_done,
                    'status': 'inbound',
                })

            # Update outbound orders
            if getattr(picking.picking_type_id, 'code', '') != 'outgoing' and picking.outbound_order_id:
                origin_picking = self.search([('name', '=', picking.origin)], limit=1)
                if not origin_picking:
                    picking.outbound_order_id.write({
                        'picking_PICK_date': picking.date_done,
                        'status': 'picking',
                    })
                    
            if getattr(picking.picking_type_id, 'code', '') == 'outgoing':
                origin_picking = self.search([('name', '=', picking.origin)], limit=1)
                if origin_picking and origin_picking.picking_type_id and getattr(origin_picking.picking_type_id, 'code', '') == 'internal':
                    try:
                        if origin_picking.outbound_order_id:
                            origin_picking.outbound_order_id.write({
                                'picking_Out': picking.id,
                                'picking_Out_date': picking.date_done,
                                'status': 'outbound',
                            })
                    except Exception:
                        picking.message_post(body=_('Warning: could not update outbound order link for %s') % picking.display_name)

            # Ensure separate deliveries for internal transfers
            if picking.picking_type_id and getattr(picking.picking_type_id, 'code', '') == 'internal' and picking.state == 'done':
                try:
                    picking._ensure_separate_deliveries()
                except Exception:
                    picking.message_post(body=_('Warning: could not ensure separate delivery for %s') % picking.display_name)

        return res

    def _pre_validate_separation(self):
        """Final separation check before validation"""
        for picking in self:
            if picking._has_disable_auto_merge_routes() and len(picking.move_ids) > 1:
                # This picking should only contain moves from the same source
                self._ensure_picking_purity(picking)

    def _ensure_picking_purity(self, picking):
        """Ensure picking only contains moves from the same source"""
        origins = set()
        for move in picking.move_ids:
            if move.origin:
                origins.add(move.origin)
            elif move.picking_id and move.picking_id.origin:
                origins.add(move.picking_id.origin)
        
        if len(origins) > 1:
            # Contains moves from multiple origins - need to separate
            self._separate_by_origin(picking, origins)

    def _separate_by_origin(self, picking, origins):
        """Separate picking by origin"""
        moves_by_origin = {}
        for move in picking.move_ids:
            origin = move.origin or (move.picking_id.origin if move.picking_id else '')
            if origin not in moves_by_origin:
                moves_by_origin[origin] = self.env['stock.move']
            moves_by_origin[origin] |= move
        
        # Keep first origin in original picking, create new pickings for others
        if moves_by_origin:
            first_origin = list(moves_by_origin.keys())[0]
            moves_to_keep = moves_by_origin.pop(first_origin)
            
            for origin, moves in moves_by_origin.items():
                if moves:
                    new_picking_vals = {
                        'move_ids': [],
                        'move_line_ids': [],
                        'backorder_id': False,
                        'origin': origin,
                        'picking_type_id': picking.picking_type_id.id,
                        'location_id': picking.location_id.id,
                        'location_dest_id': picking.location_dest_id.id,
                        'partner_id': picking.partner_id.id,
                        'scheduled_date': picking.scheduled_date,
                        'group_id': False,
                    }
                    
                    new_picking = picking.copy(new_picking_vals)
                    moves.write({'picking_id': new_picking.id})
                    if moves.move_line_ids:
                        moves.move_line_ids.write({'picking_id': new_picking.id})

    def _ensure_separate_deliveries(self):
        """Ensure each internal transfer creates a separate delivery"""
        outgoing_moves = self.move_ids.mapped('move_dest_ids').filtered(
            lambda m: m.picking_type_id.code == 'outgoing' and m.state not in ('done', 'cancel')
        )
        
        if outgoing_moves:
            deliveries = outgoing_moves.mapped('picking_id')
            
            for delivery in deliveries:
                internal_origins = set()
                for move in delivery.move_ids:
                    if move.move_orig_ids:
                        for orig_move in move.move_orig_ids:
                            if orig_move.picking_id and orig_move.picking_type_id.code == 'internal':
                                internal_origins.add(orig_move.picking_id.id)
                
                if len(internal_origins) > 1:
                    self._split_delivery_by_transfer_origin(delivery)

    def _split_delivery_by_transfer_origin(self, delivery):
        """Split delivery based on internal transfer origin"""
        moves_by_origin = {}
        for move in delivery.move_ids:
            internal_origin_id = None
            if move.move_orig_ids:
                for orig_move in move.move_orig_ids:
                    if orig_move.picking_id and orig_move.picking_type_id.code == 'internal':
                        internal_origin_id = orig_move.picking_id.id
                        break
            
            if internal_origin_id not in moves_by_origin:
                moves_by_origin[internal_origin_id] = self.env['stock.move']
            moves_by_origin[internal_origin_id] |= move
        
        if moves_by_origin:
            first_origin = list(moves_by_origin.keys())[0]
            moves_to_keep = moves_by_origin.pop(first_origin)
            
            for origin_id, moves in moves_by_origin.items():
                if moves:
                    internal_transfer = self.env['stock.picking'].browse(origin_id)
                    new_delivery_vals = {
                        'move_ids': [],
                        'move_line_ids': [],
                        'backorder_id': False,
                        'origin': internal_transfer.name,
                        'picking_type_id': delivery.picking_type_id.id,
                        'location_id': delivery.location_id.id,
                        'location_dest_id': delivery.location_dest_id.id,
                        'partner_id': delivery.partner_id.id,
                        'scheduled_date': delivery.scheduled_date,
                        'group_id': False,
                    }
                    
                    new_delivery = delivery.copy(new_delivery_vals)
                    moves.write({'picking_id': new_delivery.id})
                    if moves.move_line_ids:
                        moves.move_line_ids.write({'picking_id': new_delivery.id})

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