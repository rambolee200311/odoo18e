import logging
from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo import _
from odoo.tools.float_utils import float_compare, float_is_zero
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



    #LINGLONG 专用创建出库调拨单
    def action_create_picking_PICK_linglong(self):
        """
        LINGLONG: Create picking, merge same products (by product+uom+src/dest+prefix),
        confirm moves, then reserve by FIFO pool.
        """
        for record in self:
            if not record.project or record.project.name != "LINGLONG":
                raise UserError(_("Only LINGLONG can create PICK type stock picking."))

            if record.state != "confirm":
                raise UserError(_("Outbound order must be confirmed before creating a stock picking."))
            if not record.pick_type:
                raise UserError(_("Picking type must be set before creating a stock picking."))
            if not record.p_date:
                raise UserError(_("Planning date must be set before creating a stock picking."))
            if not record.reference:
                raise UserError(_("Reference must be set before creating a stock picking."))

            existing_picking = self.env["stock.picking"].sudo().search([
                ("outbound_order_id", "=", record.id),
                ("picking_type_id", "=", record.pick_type.id),
                ("state", "!=", "cancel"),
            ], limit=1)
            if existing_picking:
                raise UserError(_("A stock picking already exists for this Outbound Order."))

            group = self.env["procurement.group"].sudo().search([("name", "=", record.billno)], limit=1)
            if not group:
                group = self.env["procurement.group"].create({"name": record.billno})

            picking = self.env["stock.picking"].create({
                "picking_type_id": record.pick_type.id,
                "location_id": record.pick_type.default_location_src_id.id,
                "location_dest_id": record.pick_type.default_location_dest_id.id,
                "origin": record.billno,
                "partner_id": record.unload_company.id,
                "outbound_order_id": record.id,
                "planning_date": record.p_date,
                "ref_1": record.reference,
                "load_ref": record.load_ref,
                "group_id": group.id,
            })

            # -----------------------------
            # 1) 先把 outbound 行按 key 聚合（相同产品合并）
            # key 里建议包含 prefix：prefix 不同不能合并，否则会破坏“只从某前缀包号出”
            # -----------------------------
            aggregated = {}
            for line in record.outbound_order_product_ids:
                product = line.product_id
                if not product:
                    continue
                qty = float(line.quantity or 0.0)
                if qty <= 0:
                    continue

                prefix = (line.pallet_prefix_code or "").strip()
                key = (
                    product.id,
                    product.uom_id.id,
                    picking.location_id.id,
                    picking.location_dest_id.id,
                    prefix,
                )
                if key not in aggregated:
                    aggregated[key] = {
                        "product": product,
                        "uom": product.uom_id,
                        "qty": 0.0,
                        "prefix": prefix,
                        "line_ids": [],
                    }
                aggregated[key]["qty"] += qty
                aggregated[key]["line_ids"].append(line.id)

            # -----------------------------
            # 2) 创建 move：一组一条
            # -----------------------------
            created_moves = self.env["stock.move"]
            for _key, data in aggregated.items():
                move_vals = {
                    "name": data["product"].display_name,
                    "product_id": data["product"].id,
                    "product_uom_qty": data["qty"],
                    "product_uom": data["uom"].id,
                    "picking_id": picking.id,
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                    "group_id": group.id,
                    # 不写 outbound_order_product_id#stock.move的outbound_order_product_id,可能是多条
                }
                created_moves |= self.env["stock.move"].create(move_vals)

            if record.is_auto_moves:
                record.actionReserveByPoolFifo_linglong(picking)
            if created_moves:
                created_moves._action_confirm(merge=True)

            record.picking_PICK = picking.id

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Stock Picking Created"),
                "message": _("Stock picking has been created and reserved successfully."),
                "sticky": False,
            }
        }

    def actionReserveByPoolFifo_linglong(self, picking):
        """
        Reserve stock by:
        - Build a quant availability pool once (key = (product_id, prefix))
        - Consume pool line-by-line to avoid double spending
        - Use official-style reservation: move._update_reserved_quantity()
          (so Odoo creates/updates stock.move.line itself)
        """
        for rec in self:
            # 1) 汇总需求：按 (product_id, prefix)
            demand_map = {}
            for line in rec.outbound_order_product_ids:
                if not line.product_id:
                    continue
                qty = float(line.quantity or 0.0)
                if qty <= 0:
                    continue
                prefix = (line.pallet_prefix_code or "").strip()
                key = (line.product_id.id, prefix)
                demand_map[key] = demand_map.get(key, 0.0) + qty

            # 2) 构建库存池：按 (product_id, prefix) 获取 quants，按 in_date FIFO 排序
            pool_map = {}
            for (product_id, prefix), total_demand in demand_map.items():
                domain = [
                    ("product_id", "=", product_id),
                    ("quantity", ">", 0),
                    ("location_id.usage", "=", "internal"),
                ]
                if prefix:
                    domain.append(("package_id.name", "ilike", f"%{prefix}%"))

                # search must sudo
                quants = self.env["stock.quant"].sudo().search(domain, order="in_date asc, id asc")

                buckets = []
                total_available = 0.0
                product = self.env["product.product"].browse(product_id)
                rounding = product.uom_id.rounding

                for q in quants:
                    avail = q.quantity - q.reserved_quantity
                    if float_compare(avail, 0, precision_rounding=rounding) > 0:
                        buckets.append({
                            "location_id": q.location_id,
                            "lot_id": q.lot_id,
                            "package_id": q.package_id,
                            "owner_id": q.owner_id,
                            "remaining": avail,
                        })
                        total_available += avail

                if float_compare(total_available, total_demand, precision_rounding=rounding) < 0:
                    raise UserError(_(
                        "Insufficient available stock for %s%s! Required: %s, Available: %s, Shortfall: %s"
                    ) % (
                                        product.display_name,
                                        f" (prefix: {prefix})" if prefix else "",
                                        total_demand,
                                        total_available,
                                        (total_demand - total_available),
                                    ))

                pool_map[(product_id, prefix)] = buckets

            # 3) 找到每条 outbound 行对应的 move（因为我们 confirm 时 merge=False，所以一行一个 move 可稳定映射）
            moves = picking.move_ids_without_package.filtered(
                lambda m: m.state in ("confirmed", "waiting", "partially_available")
            )
            move_by_line = {m.outbound_order_product_id.id: m for m in moves if m.outbound_order_product_id}

            # 4) 逐行预留：从 pool 消费 remaining，用 _update_reserved_quantity 让系统生成 move line
            for line in rec.outbound_order_product_ids:
                move = move_by_line.get(line.id)
                if not move:
                    continue

                prefix = (line.pallet_prefix_code or "").strip()
                key = (line.product_id.id, prefix)
                buckets = pool_map.get(key, [])

                # move.reserved_availability 是已预留量（uom 视版本为 product_uom 或 product uom）
                # 这里按官方逻辑：缺口 = move.product_uom_qty - move.reserved_availability
                need_uom = move.product_uom_qty - move.reserved_availability
                if float_compare(need_uom, 0, precision_rounding=move.product_uom.rounding) <= 0:
                    continue

                # 转到 product.uom（quant 单位）
                need = move.product_uom._compute_quantity(
                    need_uom, move.product_id.uom_id, rounding_method="HALF-UP"
                )
                rounding = move.product_id.uom_id.rounding

                allocated_locations = []
                for b in buckets:
                    if float_compare(need, 0, precision_rounding=rounding) <= 0:
                        break
                    if float_compare(b["remaining"], 0, precision_rounding=rounding) <= 0:
                        continue

                    take = min(b["remaining"], need)

                    # 严格按 location/lot/package/owner 预留（系统负责创建/更新 move line）
                    taken = move._update_reserved_quantity(
                        take,
                        b["location_id"],
                        lot_id=b["lot_id"],
                        package_id=b["package_id"],
                        owner_id=b["owner_id"],
                        strict=True,
                    )
                    if float_is_zero(taken, precision_rounding=rounding):
                        continue

                    b["remaining"] -= taken
                    need -= taken

                    loc_name = b["location_id"].complete_name
                    if loc_name not in allocated_locations:
                        allocated_locations.append(loc_name)

                # 并发兜底：极端情况下库存被别人抢走，taken 可能小于需要
                if float_compare(need, 0, precision_rounding=rounding) > 0:
                    raise UserError(
                        _("Stock changed during reservation for %s. Please retry.") % move.product_id.display_name)

                # 你原来写 locations，这里仍保留（write 不 sudo）
                if allocated_locations:
                    line.locations = ", ".join(allocated_locations)

            # 5) 刷 move 状态（官方最后会把 assigned/partially_available 写回）
            assigned_moves = self.env["stock.move"]
            partial_moves = self.env["stock.move"]
            for m in picking.move_ids_without_package:
                if m.state not in ("confirmed", "waiting", "partially_available"):
                    continue
                if float_compare(m.reserved_availability, m.product_uom_qty,
                                 precision_rounding=m.product_uom.rounding) >= 0:
                    assigned_moves |= m
                elif float_compare(m.reserved_availability, 0, precision_rounding=m.product_uom.rounding) > 0:
                    partial_moves |= m

            if partial_moves:
                partial_moves.write({"state": "partially_available"})
            if assigned_moves:
                assigned_moves.write({"state": "assigned"})

            if not self.env.context.get("bypass_entire_pack"):
                picking._check_entire_pack()

    def action_check_available_linglong(self):
        """
        Check whether sufficient available stock exists to allocate all outbound order products.
        - 汇总需求 -> 构建可用库存池 -> 按行消费池
        - 解决：同产品多行“各自都满足，但合计不满足”的问题
        """
        all_errors = []

        for record in self:
            if record.project.name != 'LINGLONG':
                raise UserError(_("Only LINGLONG can create PICK type stock picking."))
            if not record.is_auto_moves:
                continue

            # 1) 汇总需求：key = (product_id, prefix)
            demand_map = {}
            line_list = record.outbound_order_product_ids
            for line in line_list:
                product = line.product_id
                if not product:
                    continue
                required_qty = float(line.quantity or 0.0)
                if required_qty <= 0:
                    continue
                prefix = (line.pallet_prefix_code or "").strip()
                key = (product.id, prefix)
                demand_map[key] = demand_map.get(key, 0.0) + required_qty

            # 2) 构建库存池：key -> buckets(每个 bucket 记录 remaining)，并做总量校验
            #    这里用 in_date asc 做“类 FIFO”排序（更接近你想要的先入先出思路）
            pool_map = {}
            for (product_id, prefix), total_demand in demand_map.items():
                quant_domain = [
                    ("product_id", "=", product_id),
                    ("quantity", ">", 0),
                    ("location_id.usage", "=", "internal"),
                ]
                if prefix:
                    quant_domain.append(("package_id.name", "ilike", f"%{prefix}%"))

                quants = self.env["stock.quant"].sudo().search(quant_domain, order="in_date asc, id asc")

                total_onhand_qty = 0.0
                total_reserved_qty = 0.0
                total_available_qty = 0.0
                buckets = []

                for q in quants:
                    total_onhand_qty += q.quantity
                    total_reserved_qty += q.reserved_quantity
                    avail = q.quantity - q.reserved_quantity
                    if avail > 0:
                        buckets.append({
                            "location_id": q.location_id,
                            "package_id": q.package_id,
                            "owner_id": q.owner_id,
                            "lot_id": q.lot_id,
                            "remaining": avail,
                        })
                        total_available_qty += avail

                # 日志（按 key 记录一次，避免每行刷屏）
                prod = self.env["product.product"].browse(product_id)
                _logger.info(
                    "Stock Check(Pool) - Product: %s%s, Demand: %s, On-hand: %s, Reserved: %s, Available: %s",
                    prod.display_name,
                    f" (prefix: {prefix})" if prefix else "",
                    total_demand,
                    total_onhand_qty,
                    total_reserved_qty,
                    total_available_qty,
                )

                if total_available_qty <= 0 and total_demand > 0:
                    all_errors.append(_(
                        "Insufficient available stock for %s%s! No available stock found. %s",
                        prod.display_name,
                        f" (prefix: {prefix})" if prefix else "",
                        f"Total on-hand: {total_onhand_qty}, Reserved: {total_reserved_qty}",
                    ))
                    continue

                if total_available_qty < total_demand:
                    shortfall = total_demand - total_available_qty
                    all_errors.append(_(
                        "Insufficient available stock for %s%s! Required: %s, Available: %s, Shortfall: %s units",
                        prod.display_name,
                        f" (prefix: {prefix})" if prefix else "",
                        total_demand,
                        total_available_qty,
                        shortfall,
                    ))
                    continue

                pool_map[(product_id, prefix)] = buckets

            # 3) 按行消费库存池：防止同产品多行双花
            #    这里不再报错（报错已在总量校验阶段完成）；这一步主要用于“验证逻辑一致”
            for line in line_list:
                product = line.product_id
                if not product:
                    continue
                required_qty = float(line.quantity or 0.0)
                if required_qty <= 0:
                    continue

                prefix = (line.pallet_prefix_code or "").strip()
                key = (product.id, prefix)
                buckets = pool_map.get(key, [])

                remaining_need = required_qty
                for b in buckets:
                    if remaining_need <= 0:
                        break
                    if b["remaining"] <= 0:
                        continue
                    take = min(b["remaining"], remaining_need)
                    b["remaining"] -= take
                    remaining_need -= take


                if remaining_need > 1e-9:
                    all_errors.append(_(
                        "Insufficient available stock for %s%s! Required: %s, Available: %s, Shortfall: %s units",
                        product.display_name,
                        f" (prefix: {prefix})" if prefix else "",
                        required_qty,
                        required_qty - remaining_need,
                        remaining_need,
                    ))

        if all_errors:
            raise UserError("\n".join(all_errors))

        # UX：单条记录返回通知
        if len(self) == 1:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Stock Availability Check Passed"),
                    "message": _("All products can be fully allocated based on pooled availability."),
                    "sticky": False,
                }
            }

        return True