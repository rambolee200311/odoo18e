import logging
from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta

_logger = logging.getLogger(__name__)


class InboundOrder(models.Model):
    _inherit = 'world.depot.inbound.order'    
    
    def action_create_stock_picking(self):
        """Create the related stock picking with packages and move lines."""
        for record in self:
            # Ensure the order is confirmed
            if record.state != 'confirm':
                raise UserError(_("Stock picking can only be created from confirmed orders."))
            if not record.reference:
                raise UserError(_("Reference must be set before creating a stock picking."))
            if not record.pick_type:
                raise UserError(_("Picking Type is required to create a stock picking."))
            if not record.cntr_no:
                raise UserError(_("Container No is required to create packages."))

            # Check if stock picking already exists
            existing_picking = self.env['stock.picking'].search(
                [('inbound_order_id', '=', record.id), ('state', '!=', 'cancel')], limit=1)
            if existing_picking:
                raise UserError(_("A stock picking already exists for this Inbound Order."))

            charge_of_pallet = record.project.charge_of_pallet

            # Create the stock picking
            picking = self.env['stock.picking'].create({
                'picking_type_id': record.pick_type.id,
                'location_id': record.pick_type.default_location_src_id.id,
                'location_dest_id': record.pick_type.default_location_dest_id.id,
                'origin': record.billno,
                'partner_id': record.owner.id,
                'inbound_order_id': record.id,
                'owner_id': record.owner.id,
                'bill_of_lading': record.bl_no,
                'cntrno': record.cntr_no,
                'ref_1': record.reference,
                'planning_date': record.a_date,
            })
            
            pallet_index = 1
            product_move_map = {}
            pallet_data_list = []
            
            # Collect all products for creating stock moves
            for product in record.inbound_order_product_ids:
                for pallet in product.inbound_order_product_pallet_ids:
                    product_id = pallet.product_id.id
                    
                    # Add to product move map for grouping
                    if product_id not in product_move_map:
                        product_move_map[product_id] = {
                            'product': pallet.product_id,
                            'total_quantity': 0,
                            'move_lines': []
                        }
                    
                    # Calculate total quantity for this product across all pallets
                    product_move_map[product_id]['total_quantity'] += pallet.quantity * product.pallets
                    product_move_map[product_id]['move_lines'].append({
                        'pallet_obj': pallet,
                        'quantity': pallet.quantity * product.pallets,
                    })
            
            # Create stock moves for each product
            product_moves = {}
            for product_id, product_data in product_move_map.items():
                product = product_data['product']
                total_quantity = product_data['total_quantity']
                
                if total_quantity <= 0:
                    raise UserError(_("Invalid total quantity for product '%s'.") % product.name)
                
                move = self.env['stock.move'].create({
                    'name': product.name,
                    'product_id': product_id,
                    'product_uom_qty': total_quantity,
                    'product_uom': product.uom_id.id,
                    'picking_id': picking.id,
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                    'description_picking': f"Merged move - {product.name}",
                })
                product_moves[product_id] = move

            # Now create packages and move lines for each physical pallet
            for product in record.inbound_order_product_ids:
                # Create packages for each physical pallet
                for pallet_number in range(1, int(product.pallets) + 1):
                    # Create one package per physical pallet
                    package_name = f"{record.reference}-{record.cntr_no}-{str(pallet_index).zfill(4)}"
                    package = self.env['stock.quant.package'].search([('name', '=', package_name)])
                    if not package:
                        package = self.env['stock.quant.package'].create({
                            'name': package_name,
                            'package_use': 'disposable',
                        })
                    
                    # For each product on this pallet, create move lines
                    for pallet in product.inbound_order_product_pallet_ids:
                        move = product_moves[pallet.product_id.id]
                        
                        # Create lot if product is lot tracked
                        lot = False
                        if pallet.product_id.tracking == 'lot':
                            lot_name = f"{record.a_date.strftime('%Y%m')}-{record.cntr_no}-{str(pallet_index).zfill(4)}"
                            lot = self.env['stock.lot'].search(
                                [('name', '=', lot_name),
                                ('product_id', '=', pallet.product_id.id)], limit=1)
                            if not lot:
                                lot = self.env['stock.lot'].create({
                                    'name': lot_name,
                                    'product_id': pallet.product_id.id,
                                })
                        
                        if not lot and pallet.product_id.tracking == 'lot':
                            raise UserError(
                                _("Failed to create or find lot for product '%s'.") % pallet.product_id.name)
                        
                        # Handle serial-tracked products
                        if pallet.product_id.tracking == 'serial' and record.is_scan_sn:
                            for unit_index in range(1, int(pallet.quantity) + 1):
                                self.env['stock.move.line'].create({
                                    'move_id': move.id,
                                    'picking_id': picking.id,
                                    'product_id': pallet.product_id.id,
                                    'product_uom_id': pallet.product_id.uom_id.id,
                                    'quantity': 1.00,
                                    'location_id': picking.location_id.id,
                                    'location_dest_id': picking.location_dest_id.id,
                                    'result_package_id': package.id if charge_of_pallet else False,
                                })
                        else:
                            # Create move line for this product on this pallet
                            self.env['stock.move.line'].create({
                                'move_id': move.id,
                                'picking_id': picking.id,
                                'product_id': pallet.product_id.id,
                                'product_uom_id': pallet.product_id.uom_id.id,
                                'quantity': pallet.quantity,  # Quantity per pallet
                                'location_id': picking.location_id.id,
                                'location_dest_id': picking.location_dest_id.id,
                                'lot_id': lot.id if lot else False,
                                'lot_name': lot.name if lot else False,
                                'result_package_id': package.id if charge_of_pallet else False,
                            })
                    
                    pallet_index += 1

            record.stock_picking_id = picking.id

        # Return a success message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Stock Picking Created'),
                'message': _('Stock picking with packages has been created successfully.'),
                'sticky': False,
            }
        }    
        
    def action_create_stock_picking_old2(self):
        """Create the related stock picking with packages and move lines."""
        for record in self:
            # Ensure the order is confirmed
            if record.state != 'confirm':
                raise UserError(_("Stock picking can only be created from confirmed orders."))
            if not record.reference:
                raise UserError(_("Reference must be set before creating a stock picking."))
            if not record.pick_type:
                raise UserError(_("Picking Type is required to create a stock picking."))
            if not record.cntr_no:
                raise UserError(_("Container No is required to create packages."))

            # Check if stock picking already exists
            existing_picking = self.env['stock.picking'].search(
                [('inbound_order_id', '=', record.id), ('state', '!=', 'cancel')], limit=1)
            if existing_picking:
                raise UserError(_("A stock picking already exists for this Inbound Order."))

            charge_of_pallet = record.project.charge_of_pallet

            # Create the stock picking
            picking = self.env['stock.picking'].create({
                'picking_type_id': record.pick_type.id,
                'location_id': record.pick_type.default_location_src_id.id,
                'location_dest_id': record.pick_type.default_location_dest_id.id,
                'origin': record.billno,
                'partner_id': record.owner.id,
                'inbound_order_id': record.id,
                'owner_id': record.owner.id,
                'bill_of_lading': record.bl_no,
                'cntrno': record.cntr_no,
                'ref_1': record.reference,
                'planning_date': record.a_date,
            })
            pallet_index = 1

            # Group same products together to merge quantities
            product_pallet_map = {}
            for product in record.inbound_order_product_ids:
                for pallet in product.inbound_order_product_pallet_ids:
                    product_id = pallet.product_id.id
                    if product_id not in product_pallet_map:
                        product_pallet_map[product_id] = {
                            'product': pallet.product_id,
                            'total_quantity': 0,
                            'pallets': []
                        }
                    
                    # Calculate total quantity for this pallet (considering number of pallets)
                    pallet_quantity = pallet.quantity * product.pallets
                    product_pallet_map[product_id]['total_quantity'] += pallet_quantity
                    product_pallet_map[product_id]['pallets'].append({
                        'pallet_obj': pallet,
                        'quantity': pallet_quantity,
                        'product_pallets': product.pallets
                    })

            # Create one stock move for each product (merged)
            for product_id, product_data in product_pallet_map.items():
                product = product_data['product']
                total_quantity = product_data['total_quantity']
                
                if total_quantity <= 0:
                    raise UserError(_("Invalid total quantity for product '%s'.") % product.name)
                
                # Create stock move for the merged product
                move = self.env['stock.move'].create({
                    'name': product.name,
                    'product_id': product_id,
                    'product_uom_qty': total_quantity,
                    'product_uom': product.uom_id.id,
                    'picking_id': picking.id,
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                    'description_picking': f"Merged move - {product.name}",
                })

                # Create move lines for each pallet but with merged product quantities
                for pallet_data in product_data['pallets']:
                    pallet = pallet_data['pallet_obj']
                    pallet_quantity = pallet_data['quantity']
                    
                    # Create package
                    package_name = f"{record.reference}-{record.cntr_no}-{str(pallet_index).zfill(4)}"
                    package = self.env['stock.quant.package'].search([('name', '=', package_name)])
                    if not package:
                        package = self.env['stock.quant.package'].create({
                            'name': package_name,
                            'package_use': 'disposable',
                        })
                    
                    # Create lot if product is lot tracked
                    lot = False
                    if pallet.product_id.tracking == 'lot':
                        lot_name = f"{record.a_date.strftime('%Y%m')}-{record.cntr_no}-{str(pallet_index).zfill(4)}"
                        lot = self.env['stock.lot'].search(
                            [('name', '=', lot_name),
                             ('product_id', '=', pallet.product_id.id)], limit=1)
                        if not lot:
                            lot = self.env['stock.lot'].create({
                                'name': lot_name,
                                'product_id': pallet.product_id.id,
                            })
                        lot = self.env['stock.lot'].search(
                            [('name', '=', lot_name),
                             ('product_id', '=', pallet.product_id.id)], limit=1)
                    if not lot and pallet.product_id.tracking == 'lot':
                        raise UserError(
                            _("Failed to create or find lot for product '%s'.") % pallet.product_id.name)

                    # Handle serial-tracked products with scanning enabled
                    if pallet.product_id.tracking == 'serial' and record.is_scan_sn:
                        for unit_index in range(1, int(pallet.quantity) + 1):
                            self.env['stock.move.line'].create({
                                'move_id': move.id,
                                'picking_id': picking.id,
                                'product_id': pallet.product_id.id,
                                'product_uom_id': pallet.product_id.uom_id.id,
                                'quantity': 1.00,  # Planned quantity
                                'location_id': picking.location_id.id,
                                'location_dest_id': picking.location_dest_id.id,
                                'result_package_id': package.id if charge_of_pallet else False,
                            })
                    else:
                        # Create stock move line with merged product quantity
                        self.env['stock.move.line'].create({
                            'move_id': move.id,
                            'picking_id': picking.id,
                            'product_id': pallet.product_id.id,
                            'product_uom_id': pallet.product_id.uom_id.id,
                            'quantity': pallet_quantity,  # Planned quantity
                            'location_id': picking.location_id.id,
                            'location_dest_id': picking.location_dest_id.id,                            
                            'lot_id': lot.id if lot else False,
                            'lot_name': lot.name if lot else False,
                            'result_package_id': package.id if charge_of_pallet else False,
                        })  

                    pallet_index += 1

            record.stock_picking_id = picking.id

        # Return a success message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Stock Picking Created'),
                'message': _('Stock picking with packages has been created successfully.'),
                'sticky': False,
            }
        }