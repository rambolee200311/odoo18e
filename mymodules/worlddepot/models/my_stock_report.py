from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class StockReportContainer(models.Model):
    _name = 'world.depot.store.report.container'
    _description = 'Stock Report Container'
    
    name=fields.Char(string='Report Name')
    container_id = fields.Char(string='Container ID', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)   
    product_category_id = fields.Many2one('product.category', string='Product Category', readonly=True)
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure', readonly=True) 
    product_barcode = fields.Char(string='Product Barcode', readonly=True)
    inbound_quantity = fields.Float(string='Inbound Quantity', readonly=True)
    outbound_quantity = fields.Float(string='Outbound Quantity', readonly=True)
    output_quantity = fields.Float(string='Output Quantity', readonly=True)
    onhand_quantity = fields.Float(string='On-hand Quantity', readonly=True)
    
    @api.model
    def init(self):
        """Module init hook: populate or refresh the report table."""
        # self._init_report()
    
    def _init_report(self):
        try:
            # Clear existing data
            self.env.cr.execute(f"DELETE FROM {self._table}")
            self.env.cr.flush()

            # Get internal locations
            internal_locations = self.env['stock.location'].search([
                ('usage', '=', 'internal')
            ])
            
            # Get stock quants with the filters
            quants = self.env['stock.quant'].search([
                ('location_id', 'in', internal_locations.ids)
            ])
            
            # Dictionary to aggregate by container + product
            container_product_dict = {}
            
            for quant in quants:
                # Get container information
                container_name = ''
                container_number = ''
                
                if quant.product_id.tracking == 'lot' and quant.lot_id and quant.lot_id.name:
                    container_name = quant.lot_id.name
                    parts = container_name.split('-')
                    # Use full container name for lot tracking
                    container_number = container_name
                    _logger.info(f"Lot container: {container_name} -> {container_number}")
                elif quant.package_id and quant.package_id.name:
                    container_name = quant.package_id.name
                    parts = container_name.split('-')
                    # Use full container name for package tracking to distinguish between packages
                    container_number = container_name
                    _logger.info(f"Package container: {container_name} -> {container_number}")
                
                # Create unique key: container + product
                key = (container_number, quant.product_id.id)
                
                if key not in container_product_dict:
                    # First time seeing this container+product combination
                    # Calculate all moves for this container + product
                    
                    # Build base domain for moves
                    move_domain = [
                        ('product_id', '=', quant.product_id.id),
                        ('state', '=', 'done')
                    ]
                    
                    # Initialize filters
                    lot_id_filter = None
                    package_id_filter = None
                    result_package_id_filter = None
                    
                    # Add container filter based on tracking type
                    if quant.product_id.tracking == 'lot' and quant.lot_id:
                        lot_id_filter = quant.lot_id.id
                        move_domain.append(('lot_id', '=', lot_id_filter))
                        _logger.info(f"Searching moves for lot: {quant.lot_id.name}")
                    elif quant.package_id:
                        # For inbound, we should use result_package_id
                        result_package_id_filter = quant.package_id.id
                        package_id_filter = quant.package_id.id
                        _logger.info(f"Searching moves for package: {quant.package_id.name}")
                    
                    # Calculate inbound quantity - moves to internal locations
                    inbound_domain = move_domain + [
                        ('location_id.usage', '=', 'supplier'),
                        ('location_dest_id', 'in', internal_locations.ids)
                    ]
                    
                    # Key fix: use result_package_id for inbound
                    if result_package_id_filter:
                        inbound_domain.append(('result_package_id', '=', result_package_id_filter))
                        _logger.info(f"Adding result_package filter for inbound: {result_package_id_filter}")
                    elif lot_id_filter:
                        inbound_domain.append(('lot_id', '=', lot_id_filter))
                    
                    inbound_moves = self.env['stock.move.line'].search(inbound_domain)
                    inbound_qty = sum(inbound_moves.mapped('qty_done'))
                    
                    # Log inbound moves for detailed debugging
                    _logger.info(f"Inbound moves found: {len(inbound_moves)} for product {quant.product_id.display_name}, container {container_number}")
                    for move in inbound_moves:
                        _logger.info(f"  Inbound: {move.qty_done} units, "
                                f"From: {move.location_id.display_name}, "
                                f"To: {move.location_dest_id.display_name}, "
                                f"Package: {move.package_id.name if move.package_id else 'None'}, "
                                f"Result Package: {move.result_package_id.name if move.result_package_id else 'None'}")
                    
                    # Calculate outbound quantity - moves from internal locations to customer
                    outbound_domain = move_domain + [
                        ('location_id', 'in', internal_locations.ids),
                        ('location_dest_id.usage', '=', 'customer'),                        
                    ]
                    
                    # For outbound, use package_id (source package)
                    if package_id_filter:
                        outbound_domain.append(('package_id', '=', package_id_filter))
                        _logger.info(f"Adding package filter for outbound: {package_id_filter}")
                    elif lot_id_filter:
                        outbound_domain.append(('lot_id', '=', lot_id_filter))
                    
                    outbound_moves = self.env['stock.move.line'].search(outbound_domain)
                    outbound_qty = sum(outbound_moves.mapped('qty_done'))
                    
                    # Log outbound moves for debugging
                    _logger.info(f"Outbound moves found: {len(outbound_moves)} for product {quant.product_id.display_name}, container {container_number}")
                    for move in outbound_moves:
                        _logger.info(f"  Outbound: {move.qty_done} units, "
                                f"From: {move.location_id.display_name}, "
                                f"To: {move.location_dest_id.display_name}, "
                                f"Package: {move.package_id.name if move.package_id else 'None'}")
                    
                    # Calculate current quantities
                    output_qty = quant.quantity if quant.location_id.name == 'Output' else 0
                    onhand_qty = 0 if quant.location_id.name == 'Output' else quant.quantity
                    
                    container_id=container_number.split('-')[1] if '-' in container_number else container_number
                    
                    container_product_dict[key] = {
                        'container_id': container_id or '',
                        'product_id': quant.product_id.id,
                        'product_category_id': quant.product_id.categ_id.id,
                        'product_uom_id': quant.product_uom_id.id,
                        'product_barcode': quant.product_id.barcode or '',
                        'inbound_quantity': inbound_qty,
                        'outbound_quantity': outbound_qty,
                        'output_quantity': output_qty,
                        'onhand_quantity': onhand_qty,
                    }
                    
                    _logger.info(f"Container: {container_number}, Product: {quant.product_id.display_name}, "
                            f"Inbound: {inbound_qty}, Outbound: {outbound_qty}, Onhand: {onhand_qty}")
                else:
                    # Aggregate quantities for same container + product
                    container_product_dict[key]['output_quantity'] += quant.quantity if quant.location_id.name == 'Output' else 0
                    container_product_dict[key]['onhand_quantity'] += 0 if quant.location_id.name == 'Output' else quant.quantity
            
            # Convert to list
            inverted_records = list(container_product_dict.values())
                
            # Use batch creation method
            self._create_records_in_batches(inverted_records)
            
            self.env.cr.flush()
                            
        except Exception as e:
            _logger.error(f"Error initializing StockReportContainer: {e}")
            _logger.error("Full traceback:", exc_info=True)
    
    def _create_records_in_batches(self, records_data):
        """Batch create records to optimize performance"""
        batch_size = 1000
        for i in range(0, len(records_data), batch_size):
            batch = records_data[i:i + batch_size]
            try:
                self.create(batch)
            except Exception as batch_error:
                _logger.error(f"Error creating batch {i // batch_size}: {batch_error}")
                self._create_records_individually(batch)
    
    def _create_records_individually(self, records_data):
        """Create records one by one for handling batch creation failures"""
        for record_data in records_data:
            try:
                self.create([record_data])
            except Exception as single_error:
                _logger.error(f"Failed to create record: {record_data}. Error: {single_error}")

    def action_refresh_report(self):
        """Refresh the report table from UI"""
        try:
            self._init_report()
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }
        except Exception as e:
            _logger.error(f"Error refreshing StockReportContainer from UI: {e}")
            return False

    @api.model_create_multi
    def create(self, vals_list):
        """Override create method to support batch creation"""
        return super().create(vals_list)