from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import float_is_zero, float_compare


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
    load_ref = fields.Char(string='Loading Reference', required=False, help='Reference for the Delivery', )

    '''
    @api.constrains('bill_of_lading', 'cntrno', 'picking_type_id', 'origin_returned_picking_id')
    def _check_receipt_fields(self):
        for record in self:
            if (record.picking_type_id.code == 'incoming'
                    and not record.origin_returned_picking_id):  # 'incoming' corresponds to Receipt operation type
                if not record.bill_of_lading or not record.cntrno:
                    raise ValidationError("Bill of Lading and Container Number cannot be empty for Receipt operations.")
    '''
    # Override button_validate to enforce strict quantity control and handle custom fields
    def button_validate(self):
        # Check strict quantity control for each picking
        for picking in self:
            if picking.picking_type_id.strict_quantity_control:
                for move in picking.move_ids:
                    if move.state in ('done', 'cancel'):
                        continue
                    # If strict quantity control is enabled we compare the demand
                    # quantity with the actual done quantity. Use the move lines
                    # (with proper UoM conversion) rather than relying on
                    # `move.quantity` which can be inconsistent.
                    # First check: the aggregated field on the move
                    if float_compare(float(move.quantity or 0.0), move.product_uom_qty,
                                     precision_rounding=move.product_uom.rounding) != 0:
                        raise UserError(_(
                            "Recorded move quantity must equal demand quantity for product %s.\n"
                            "Demand: %s %s, Recorded move.quantity: %s %s\n\n"
                            "This is enforced by the operation type: %s"
                        ) % (
                                            move.product_id.display_name,
                                            move.product_uom_qty,
                                            move.product_uom.name,
                                            move.quantity,
                                            move.product_uom.name,
                                            picking.picking_type_id.name
                                        ))

                    # Second check: compute actual done quantity from move lines (with UoM conversion)
                    # Only perform this check when there are relevant move lines —
                    # this avoids re-checking `move.quantity` (already verified above).
                    relevant_lines = move.move_line_ids.filtered(lambda ml: ml.state != 'cancel' and float(ml.quantity or 0.0) > 0.0)
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
                            ) % (
                                                move.product_id.display_name,
                                                move.product_uom_qty,
                                                move.product_uom.name,
                                                done_qty,
                                                move.product_uom.name,
                                                picking.picking_type_id.name
                                            ))
        # After performing custom checks, call the original button_validate so the
        # normal Odoo validation and stock moves processing runs.
        res = super().button_validate()
        # Propagate Bill of Lading / Container info to lots when present.
        for picking in self:
            for move_line in picking.move_line_ids:
                if move_line.lot_id and not (move_line.lot_id.bill_of_lading or move_line.lot_id.cntrno):
                    move_line.lot_id.write({
                        'bill_of_lading': picking.bill_of_lading,
                        'cntrno': picking.cntrno,
                    })

            # Update inbound order only for incoming pickings
            if getattr(picking.picking_type_id, 'code', '') == 'incoming' and picking.inbound_order_id:
                picking.inbound_order_id.write({
                    'i_date': picking.date_done,
                    'status': 'inbound',
                })

            # Update outbound order for non-outgoing (set picking_PICK),
            # For outgoing pickings update the origin picking's outbound pointers
            if getattr(picking.picking_type_id, 'code', '') != 'outgoing':
                if picking.outbound_order_id:
                    origin_picking = self.search([('name', '=', picking.origin)], limit=1)
                    if not origin_picking:
                        picking.outbound_order_id.write({
                            'picking_PICK_date': picking.date_done,
                            'status': 'picking',
                        })
            if getattr(picking.picking_type_id, 'code', '') == 'outgoing':
                # outgoing picking: attempt to find origin picking and set its outbound pointers
                origin_picking = self.search([('name', '=', picking.origin)], limit=1)
                if origin_picking:
                    # Only proceed if the origin picking is an internal transfer
                    # (i.e. picking type code == 'internal'). This ensures we
                    # treat transfer-originated pickings as transfers/returns.
                    if origin_picking.picking_type_id and getattr(origin_picking.picking_type_id, 'code', '') == 'internal':
                        try:
                            if origin_picking.outbound_order_id:
                                origin_picking.outbound_order_id.write({
                                    'picking_Out': picking.id,
                                    'picking_Out_date': picking.date_done,
                                    'status': 'outbound',
                                })
                        except Exception:
                            picking.message_post(body=_('Warning: could not update outbound order link for %s') % picking.display_name)

        return res
        
    # Comprehensive reverse validation method                        
    def button_reverse_validate(self):    
        # Comprehensive reverse validation with complete stock recovery including:
        # - stock.quant quantity restoration
        # - stock.lot location and quantity recovery  
        # - stock.location level recalculation
        # - Package and owner restoration

        for picking in self:
            # Server-side permission check: only Inventory Managers or System
            # Administrators are allowed to perform reverse validate. The view
            # already hides the button for others, but enforce it on the server
            # to prevent RPC abuse.
            if not (self.env.user.has_group('stock.group_stock_manager') or
                    self.env.user.has_group('base.group_system')):
                raise UserError(_("You are not allowed to perform a reverse validation. Contact your administrator."))
            if picking.state != 'done':
                raise UserError(_("You can only reverse validate transfers that are in 'Done' state."))
            # If this is an internal transfer, look for outgoing deliveries
            # whose origin/source document equals this picking's name. If found,
            # remove them before continuing the reverse. Use sudo to ensure
            # the unlink can proceed even if the calling user lacks unlink
            # rights; still, try to cancel first when unlink fails.
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
                            # Do not attempt to automatically remove deliveries that are already done
                            if d.state == 'done':
                                raise UserError(_("Cannot automatically remove dependent delivery %s because it is in 'done' state. Please reverse or cancel it first.") % d.display_name)
                            # Capture the display name before any unlink to avoid MissingRecordError
                            d_display = d.display_name
                            try:
                                d.unlink()
                                removed.append(d_display)
                            except Exception:
                                # Try to cancel then unlink
                                try:
                                    d.action_cancel()
                                except Exception:
                                    # ignore; we'll surface failure below
                                    pass
                                try:
                                    d.unlink()
                                    removed.append(d_display)
                                except Exception as e:
                                    raise UserError(_("Failed to remove dependent delivery %s: %s") % (d_display, e))
                        if removed:
                            picking.message_post(body=_("Automatically removed dependent deliveries: %s") % (', '.join(removed)))
            except UserError:
                # re-raise permission/operation errors
                raise
            except Exception:
                # Non-fatal: don't block reverse for unexpected errors here,
                # surface a friendly message and continue.
                picking.message_post(body=_("Warning: could not automatically remove related deliveries for %s") % (picking.display_name,))
            
            # Verify no downstream moves exist. Guard against MissingRecordError
            # when dependent pickings were unlinked earlier in this transaction
            downstream_moves = picking.move_ids.move_dest_ids.filtered(lambda m: m.state != 'cancel')
            # Keep only moves whose picking still exists in the DB
            downstream_moves = downstream_moves.filtered(lambda m: m.picking_id and m.picking_id.exists())
            if downstream_moves:
                # Resolve picking names from a fresh browse to avoid touching possibly-unlinked cached records
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
                            self._reverse_quant_impact(move_line, quant_modifications)

                            # Reverse lot location if applicable
                            self._reverse_lot_location(move_line)

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
                    # Invalidate and explicitly call the compute methods that depend on quants so
                    # UI and related logic reflect the new quantities.
                    if locations_to_recompute:
                        # Some Odoo builds may not expose `invalidate_cache` on recordsets.
                        # To be maximally compatible, browse a fresh recordset for the
                        # affected locations and call the compute methods directly.
                        locs = self.env['stock.location'].browse(locations_to_recompute.ids)
                        try:
                            locs._compute_weight()
                        except Exception:
                            # If compute fails for any reason, continue without blocking rollback
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
                    self._rollback_quant_modifications(quant_modifications)
                    raise UserError(_("Reverse validation failed: %s") % str(e))
            
            return True

    # Helper methods for reverse validation
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

    # Helper to reverse lot location if moved
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

    # Helper to rollback quant modifications on error
    def _rollback_quant_modifications(self, modifications):
        """Rollback quant modifications in case of error"""
        for operation, quant_id, quantity in modifications:
            quant = self.env['stock.quant'].browse(quant_id)
            if quant.exists():
                if operation == 'decrement':
                    quant.quantity += quantity
                elif operation == 'increment':
                    quant.quantity -= quantity

        # Do not call button_validate or perform other operations here.
        # Rollback should only revert quant changes to restore previous stock state.
        return True

    # resetting their state to "draft"
    def delete_done_pickings(self):
        # Prompt user for confirmation
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


# models/stock_lot.py
class StockLot(models.Model):
    _inherit = 'stock.lot'

    bill_of_lading = fields.Char('Bill of Lading')
    cntrno = fields.Char('Container Number')


class StockLocation(models.Model):
    _inherit = 'stock.location'

    def _get_removal_strategy_order(self, removal_strategy):
        if removal_strategy == 'fifo':
            # 改为按时间戳升序排列
            return 'date, id'
        return super(StockLocation, self)._get_removal_strategy_order(removal_strategy)


class StockMove(models.Model):
    _inherit = 'stock.move'

    # InboundOrderProductsOfPallet's ID
    inbound_order_product_pallet_id = fields.Integer('Inbound Order Product Pallet ID', )
    nine_digit_linglong_code = fields.Char(
        string="Nine Digit Linglong Code",
        related='product_id.nine_digit_linglong_code',
        store=True
    )
    outbound_order_product_id = fields.Integer('Outbound Order ProductID', )

    def _prepare_merge_moves_distinct_fields(self):
        distinct_fields = super()._prepare_merge_moves_distinct_fields()
        # Only use pallet_id if set; ignore when null
        distinct_fields.append('inbound_order_product_pallet_id')
        return distinct_fields
'''
    def _merge_moves_fields(self):
        vals = super()._merge_moves_fields()
        vals['product_uom_qty'] = self[0].product_uom_qty  # 禁用数量合并
        return vals
'''
