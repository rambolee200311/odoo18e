import logging
from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo import _

_logger = logging.getLogger(__name__)


class OutboundOrder(models.Model):
    _inherit = 'world.depot.outbound.order'    
    
    def action_create_picking_PICK_old3(self):
        """
        Create a stock picking for the outbound order
        """
        # Pre-condition validation
        if self.state != 'confirm':
            raise UserError(_("Outbound order must be confirmed before creating a stock picking."))
        if not self.pick_type:
            raise UserError(_("Picking type must be set before creating a stock picking."))
        if not self.p_date:
            raise UserError(_("Planning date must be set before creating a stock picking."))
        if not self.reference:
            raise UserError(_("Reference must be set before creating a stock picking."))

        for record in self:
            # Check if stock picking already exists
            existing_picking = self.env['stock.picking'].search([
                ('outbound_order_id', '=', record.id),
                ('picking_type_id', '=', record.pick_type.id),
                ('state', '!=', 'cancel')
            ], limit=1)
            
            if existing_picking:
                raise UserError(_("A stock picking already exists for this Outbound Order."))

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
                'partner_id': record.unload_company.id,
                'outbound_order_id': record.id,
                'planning_date': record.p_date,
                'ref_1': record.reference,
                'load_ref': record.load_ref,
                'group_id': group.id,
            }
            picking = self.env['stock.picking'].create(picking_vals)

            # Create stock moves for each product line
            for product_line in record.outbound_order_product_ids:
                # Create stock move
                stock_move = self.env['stock.move'].create({
                    'name': product_line.product_id.name,
                    'product_id': product_line.product_id.id,
                    'product_uom_qty': product_line.quantity,
                    'product_uom': product_line.product_id.uom_id.id,
                    'picking_id': picking.id,
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                    'outbound_order_product_id': product_line.id,
                    'group_id': group.id,
                })
                
                # Validate stock move was created successfully
                if not stock_move.exists():
                    raise UserError(_("Failed to create stock move for product %s.") % product_line.product_id.name)
                
                if record.is_auto_moves:
                    # Direct allocation logic (no separate method)
                    moves = []
                    remaining_qty = product_line.quantity
                    allocated_locations = []
                    allocated_any = False
                    prefix = product_line.pallet_prefix_code or ''
                    
                    # Search for pallets with available stock
                    pallet_domain = [
                        ('quant_ids.quantity', '>', 0),
                        ('quant_ids.product_id', '=', product_line.product_id.id),
                        ('quant_ids.location_id.usage', '=', 'internal'),
                    ]
                    if prefix:
                        pallet_domain.append(('name', '=ilike', f'%{prefix}%'))
                    
                    all_pallets = self.env['stock.quant.package'].search(pallet_domain, order='create_date,name')
                    
                    # Filter pallets with available stock
                    for pallet in all_pallets:
                        if remaining_qty <= 0:
                            break
                        
                        # Calculate available quantity (considering reserved)
                        available_qty = sum(
                            quant.quantity - quant.reserved_quantity 
                            for quant in pallet.quant_ids 
                            if quant.product_id.id == product_line.product_id.id and quant.quantity > quant.reserved_quantity
                        )
                        
                        if available_qty <= 0:
                            continue
                        
                        alloc_qty = min(available_qty, remaining_qty)
                        allocated_any = True

                        # Record location
                        if pallet.location_id and pallet.location_id.complete_name not in allocated_locations:
                            allocated_locations.append(pallet.location_id.complete_name)

                        # Create move lines
                        if product_line.product_id.tracking == 'serial':
                            for i in range(int(alloc_qty)):
                                moves.append({
                                    'move_id': stock_move.id,
                                    'picking_id': picking.id,
                                    'product_id': product_line.product_id.id,
                                    'product_uom_id': product_line.product_id.uom_id.id,
                                    'quantity': 1,
                                    'location_id': pallet.location_id.id,
                                    'location_dest_id': picking.location_dest_id.id,
                                    'package_id': pallet.id,
                                    'owner_id': pallet.owner_id.id if pallet.owner_id else False,
                                })
                        else:
                            moves.append({
                                'move_id': stock_move.id,
                                'picking_id': picking.id,
                                'product_id': product_line.product_id.id,
                                'product_uom_id': product_line.product_id.uom_id.id,
                                'quantity': alloc_qty,
                                'location_id': pallet.location_id.id,
                                'location_dest_id': picking.location_dest_id.id,
                                'package_id': pallet.id,
                                'owner_id': pallet.owner_id.id if pallet.owner_id else False,
                            })
                        
                        remaining_qty -= alloc_qty
                        if remaining_qty <= 0:
                            break

                    # Search for non-pallet stock
                    if remaining_qty > 0:
                        no_pallet_quants = self.env['stock.quant'].search([
                            ('product_id', '=', product_line.product_id.id),
                            ('quantity', '>', 0),
                            ('location_id.usage', '=', 'internal'),
                            ('package_id', '=', False),
                        ]).filtered(lambda q: q.quantity > q.reserved_quantity)
                        
                        # Group by location
                        location_quants = {}
                        for quant in no_pallet_quants:
                            if quant.location_id.id not in location_quants:
                                location_quants[quant.location_id.id] = []
                            location_quants[quant.location_id.id].append(quant)
                        
                        # Allocate from non-pallet stock
                        for location_id, quants_in_location in location_quants.items():
                            if remaining_qty <= 0:
                                break
                            
                            available_qty = sum(
                                quant.quantity - quant.reserved_quantity 
                                for quant in quants_in_location
                            )
                            alloc_qty = min(available_qty, remaining_qty)
                            
                            if alloc_qty > 0:
                                allocated_any = True
                                location = quants_in_location[0].location_id
                                
                                if location.complete_name not in allocated_locations:
                                    allocated_locations.append(location.complete_name)
                                
                                if product_line.product_id.tracking == 'serial':
                                    for i in range(int(alloc_qty)):
                                        moves.append({
                                            'move_id': stock_move.id,
                                            'picking_id': picking.id,
                                            'product_id': product_line.product_id.id,
                                            'product_uom_id': product_line.product_id.uom_id.id,
                                            'quantity': 1,
                                            'location_id': location.id,
                                            'location_dest_id': picking.location_dest_id.id,
                                            'package_id': False,
                                            'owner_id': False,
                                        })
                                else:
                                    moves.append({
                                        'move_id': stock_move.id,
                                        'picking_id': picking.id,
                                        'product_id': product_line.product_id.id,
                                        'product_uom_id': product_line.product_id.uom_id.id,
                                        'quantity': alloc_qty,
                                        'location_id': location.id,
                                        'location_dest_id': picking.location_dest_id.id,
                                        'package_id': False,
                                        'owner_id': False,
                                    })
                                remaining_qty -= alloc_qty

                    # Handle insufficient stock if not allocated_any and product_line.quantity > 0:
                        raise UserError(_("Insufficient available stock for %s (prefix: %s)! No allocatable stock found.") % 
                                    (product_line.product_id.name, prefix))
                    elif remaining_qty > 0:
                        raise UserError(_("Insufficient available stock for %s (prefix: %s)! Shortfall: %s units") %
                                    (product_line.product_id.name, prefix, remaining_qty))

                    # Record locations
                    try:
                        if allocated_locations:
                            product_line.locations = ', '.join(allocated_locations)
                    except Exception as e:
                        _logger.exception('Failed to write locations for product line %s: %s', product_line.id, str(e))

                    # Create move lines
                    if moves:
                        try:
                            self.env['stock.move.line'].create(moves)
                            if not stock_move.exists():
                                _logger.error('Stock move %s was deleted before confirmation', stock_move.id)
                                continue
                            # Process the stock move
                            stock_move._action_confirm()
                            if not stock_move.exists():
                                _logger.error('Stock move %s was deleted during confirmation', stock_move.id)
                                continue
                            stock_move._action_assign()
                            
                            if stock_move.state != 'assigned':
                                _logger.warning('Stock move %s could not be fully assigned. State: %s', 
                                            stock_move.id, stock_move.state)
                            else:
                                _logger.info('Stock move %s successfully assigned. Reserved quantity: %s', 
                                        stock_move.id, stock_move.quantity)
                        except Exception as e:
                            _logger.error('Error creating move lines for product line %s: %s', product_line.id, str(e))
                            raise

            # Update the outbound order with the picking reference
            record.picking_PICK = picking.id

            # Return a success message
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Stock Picking Created'),
                    'message': _('Stock picking has been created successfully.'),
                    'sticky': False,
                }
            }    
    
    def action_create_picking_PICK(self):
        """
        Create a stock picking for the outbound order
        """
        # Pre-condition validation
        if self.state != 'confirm':
            raise UserError(_("Outbound order must be confirmed before creating a stock picking."))
        if not self.pick_type:
            raise UserError(_("Picking type must be set before creating a stock picking."))
        if not self.p_date:
            raise UserError(_("Planning date must be set before creating a stock picking."))
        if not self.reference:
            raise UserError(_("Reference must be set before creating a stock picking."))

        for record in self:
            # Check if stock picking already exists
            existing_picking = self.env['stock.picking'].search([
                ('outbound_order_id', '=', record.id),
                ('picking_type_id', '=', record.pick_type.id),
                ('state', '!=', 'cancel')
            ], limit=1)
            
            if existing_picking:
                raise UserError(_("A stock picking already exists for this Outbound Order."))

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
                'partner_id': record.unload_company.id,
                'outbound_order_id': record.id,
                'planning_date': record.p_date,
                'ref_1': record.reference,
                'load_ref': record.load_ref,
                'group_id': group.id,
            }
            picking = self.env['stock.picking'].create(picking_vals)

            # Create stock moves for each product line
            for product_line in record.outbound_order_product_ids:
                # Create stock move
                stock_move = self.env['stock.move'].create({
                    'name': product_line.product_id.name,
                    'product_id': product_line.product_id.id,
                    'product_uom_qty': product_line.quantity,
                    'product_uom': product_line.product_id.uom_id.id,
                    'picking_id': picking.id,
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                    'outbound_order_product_id': product_line.id,
                    'group_id': group.id,
                })
                
                # Validate stock move was created successfully
                if not stock_move.exists():
                    raise UserError(_("Failed to create stock move for product %s.") % product_line.product_id.name)
                
                if record.is_auto_moves:
                    # SIMPLIFIED FIX: Use direct stock.quant search like action_check_available
                    moves = []
                    remaining_qty = product_line.quantity
                    allocated_locations = []
                    prefix = product_line.pallet_prefix_code or ''
                    
                    # Get available stock using the same method as stock check
                    quant_domain = [
                        ('product_id', '=', product_line.product_id.id),
                        ('quantity', '>', 0),
                        ('location_id.usage', '=', 'internal'),
                    ]
                    
                    # Add prefix filter if specified
                    if prefix:
                        quant_domain.append(('package_id.name', '=ilike', f'%{prefix}%'))
                    
                    quants = self.env['stock.quant'].search(quant_domain)
                    
                    # Filter quants with available quantity
                    available_quants = []
                    for quant in quants:
                        available_qty = quant.quantity - quant.reserved_quantity
                        if available_qty > 0:
                            available_quants.append({
                                'quant': quant,
                                'available_qty': available_qty,
                                'location': quant.location_id,
                                'package': quant.package_id,
                                'owner': quant.owner_id
                            })
                    
                    # Allocate from available quants
                    for alloc_quant in available_quants:
                        if remaining_qty <= 0:
                            break
                        
                        alloc_qty = min(alloc_quant['available_qty'], remaining_qty)
                        
                        # Record location
                        location_name = alloc_quant['location'].complete_name
                        if location_name not in allocated_locations:
                            allocated_locations.append(location_name)

                        # Create move lines
                        if product_line.product_id.tracking == 'serial':
                            for i in range(int(alloc_qty)):
                                moves.append({
                                    'move_id': stock_move.id,
                                    'picking_id': picking.id,
                                    'product_id': product_line.product_id.id,
                                    'product_uom_id': product_line.product_id.uom_id.id,
                                    'quantity': 1,
                                    'location_id': alloc_quant['location'].id,
                                    'location_dest_id': picking.location_dest_id.id,
                                    'package_id': alloc_quant['package'].id if alloc_quant['package'] else False,
                                    'owner_id': alloc_quant['owner'].id if alloc_quant['owner'] else False,
                                })
                        else:
                            moves.append({
                                'move_id': stock_move.id,
                                'picking_id': picking.id,
                                'product_id': product_line.product_id.id,
                                'product_uom_id': product_line.product_id.uom_id.id,
                                'quantity': alloc_qty,
                                'location_id': alloc_quant['location'].id,
                                'location_dest_id': picking.location_dest_id.id,
                                'package_id': alloc_quant['package'].id if alloc_quant['package'] else False,
                                'owner_id': alloc_quant['owner'].id if alloc_quant['owner'] else False,
                            })
                        
                        remaining_qty -= alloc_qty
                        if remaining_qty <= 0:
                            break

                    # Handle insufficient stock
                    if remaining_qty > 0:
                        total_available = sum(q['available_qty'] for q in available_quants)
                        raise UserError(_("Insufficient available stock for %s%s! Required: %s, Available: %s, Shortfall: %s units") %
                                    (product_line.product_id.name, 
                                    f" (prefix: {prefix})" if prefix else "",
                                    product_line.quantity, 
                                    total_available, 
                                    remaining_qty))

                    # Record locations
                    try:
                        if allocated_locations:
                            product_line.locations = ', '.join(allocated_locations)
                    except Exception as e:
                        _logger.exception('Failed to write locations for product line %s: %s', product_line.id, str(e))

                    # Create move lines
                    if moves:
                        try:
                            self.env['stock.move.line'].create(moves)
                            if not stock_move.exists():
                                _logger.error('Stock move %s was deleted before confirmation', stock_move.id)
                                continue
                            # Process the stock move
                            stock_move._action_confirm()
                            if not stock_move.exists():
                                _logger.error('Stock move %s was deleted during confirmation', stock_move.id)
                                continue
                            stock_move._action_assign()
                            
                            if stock_move.state != 'assigned':
                                _logger.warning('Stock move %s could not be fully assigned. State: %s', 
                                            stock_move.id, stock_move.state)
                            else:
                                _logger.info('Stock move %s successfully assigned. Reserved quantity: %s', 
                                        stock_move.id, stock_move.quantity)
                        except Exception as e:
                            _logger.error('Error creating move lines for product line %s: %s', product_line.id, str(e))
                            raise

            # Update the outbound order with the picking reference
            record.picking_PICK = picking.id

            # Return a success message
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Stock Picking Created'),
                    'message': _('Stock picking has been created successfully.'),
                    'sticky': False,
                }
            }
   
    def action_check_available(self):
        """
        Check whether sufficient available stock exists to allocate all outbound order products.
        """
        all_errors = []
        for record in self:
            for product_line in record.outbound_order_product_ids:
                if not record.is_auto_moves:
                    continue

                product_id = product_line.product_id.id
                required_qty = float(product_line.quantity or 0)
                prefix = product_line.pallet_prefix_code or ''
                
                # Get all relevant stock records
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', product_id),
                    ('quantity', '>', 0),
                    ('location_id.usage', '=', 'internal'),
                ])
                
                # Calculate total on-hand quantity
                total_onhand_qty = sum(quants.mapped('quantity'))
                total_reserved_qty = sum(quants.mapped('reserved_quantity'))
                total_available_qty = total_onhand_qty - total_reserved_qty
                
                _logger.info(
                    "Stock Check - Product: %s, Required: %s, Total on-hand: %s, Total reserved: %s, Available: %s", 
                    product_line.product_id.name, required_qty, total_onhand_qty, total_reserved_qty, total_available_qty
                )
                
                # Initialize prefix-specific variables
                prefix_onhand_qty = 0
                prefix_reserved_qty = 0
                prefix_available_qty = 0
                
                # If pallet prefix is specified, check matching pallet stock
                if prefix:
                    # Get all pallets matching the prefix
                    matching_packages = self.env['stock.quant.package'].search([
                        ('name', 'ilike', f'%{prefix}%')
                    ])
                    
                    if matching_packages:
                        # Only calculate stock from matching pallets
                        prefix_quants = quants.filtered(
                            lambda q: q.package_id and q.package_id in matching_packages
                        )
                        prefix_onhand_qty = sum(prefix_quants.mapped('quantity'))
                        prefix_reserved_qty = sum(prefix_quants.mapped('reserved_quantity'))
                        prefix_available_qty = prefix_onhand_qty - prefix_reserved_qty
                        
                        # Use available quantity from matching pallets
                        available_qty = prefix_available_qty
                    else:
                        # No pallets found matching the prefix
                        _logger.warning("No packages found matching prefix '%s' for product %s", 
                                      prefix, product_line.product_id.name)
                        available_qty = 0
                else:
                    # No prefix specified, use all stock
                    available_qty = total_available_qty
                
                # Check if stock is sufficient
                if available_qty <= 0 and required_qty > 0:
                    all_errors.append(_(
                        "Insufficient available stock for %s%s! No available stock found.%s", 
                        product_line.product_id.name,
                        f" (prefix: {prefix})" if prefix else "",
                        f" Total on-hand: {total_onhand_qty}, Reserved: {total_reserved_qty}" 
                        if not prefix else f" Matching pallets on-hand: {prefix_onhand_qty}, Reserved: {prefix_reserved_qty}"
                    ))
                elif available_qty < required_qty:
                    shortfall = required_qty - available_qty
                    all_errors.append(_(
                        "Insufficient available stock for %s%s! Required: %s, Available: %s, Shortfall: %s units", 
                        product_line.product_id.name,
                        f" (prefix: {prefix})" if prefix else "",
                        required_qty, available_qty,shortfall                      
                    ))

        if all_errors:
            raise UserError('\n'.join(all_errors))
        
         # If single record call from UI, return a client notification for UX; otherwise just True
        if len(self) == 1:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Stock Availability Check Passed'),
                    'message': _('All products can be fully allocated from matching pallets.'),
                    'sticky': False,
                }
            }
        
        return True