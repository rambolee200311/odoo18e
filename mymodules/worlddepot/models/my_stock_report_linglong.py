from odoo import models, fields, api, _
from datetime import datetime, time
import logging

_logger = logging.getLogger(__name__)

class MyStockReportLinglong(models.Model):
    _name = 'world.depot.store.report.linglong'
    _description = 'Stock Report for Linglong'
    
    from_date = fields.Datetime(string='From Date', required=True, default=fields.Datetime.now)
    to_date = fields.Datetime(string='To Date', required=True, default=fields.Datetime.now)
    container_no = fields.Char(string='Container No')
    product_id = fields.Many2one('product.product', string='Product')
    products_ids = fields.One2many('world.depot.store.report.linglong.products', 'report_id', string='Products')
    
    def _get_end_of_day_datetime(self, for_date=None,type='from'):
        """
        Calculate the end of day (23:59:59) for a given date, considering Odoo's timezone handling.
        
        :param for_date: Specific date (datetime.date object), if None uses the date part of to_date
        :return: datetime object representing end of day (timezone-aware if possible)
        """
        # Determine the date to use
        if for_date is None:
            # Ensure to_date is a date object
            if isinstance(self.to_date, str):
                target_date = fields.Datetime.from_string(self.to_date).date()
            else:
                target_date = self.to_date.date()
        else:
            target_date = for_date
        
        # Combine date with end of day time
        if type=='to':
            end_of_day_naive = datetime.combine(target_date, time(23, 59, 59))
        if type=='from':
            end_of_day_naive = datetime.combine(target_date, time(0, 0, 0))    
        
        # Convert to timezone-aware datetime if context timezone is available
        if self.env.context.get('tz'):
            try:
                import pytz
                user_tz = pytz.timezone(self.env.context['tz'])
                end_of_day_aware = user_tz.localize(end_of_day_naive)
                # Convert to UTC for database storage
                end_of_day_aware = end_of_day_aware.astimezone(pytz.UTC)
                return end_of_day_aware
            except Exception as e:
                _logger.warning("Timezone conversion failed, using naive datetime: %s", e)
        
        return end_of_day_naive

    def _get_products_data(self):
        """Collect and populate report lines grouped by container and product.
        This method clears existing lines for this report and recreates them in batch.
        """
        # Clear existing lines
        if self.products_ids:
            self.products_ids.unlink()

        category_id = 11
        temp_data = {}
        
        # Get correct date ranges
        from_date_dt = self._get_end_of_day_datetime(self.from_date, 'from')
        to_date_dt = self._get_end_of_day_datetime(self.to_date, 'to')
        from_date_str = fields.Datetime.to_string(from_date_dt)
        to_date_str = fields.Datetime.to_string(to_date_dt)

        # 1. Calculate opening quantities (before from_date)
        opening_domain = [
            ('picking_id.date_done', '<', from_date_str),
            ('state', '=', 'done'),
            ('product_id.categ_id', '=', category_id),
        ]
        if self.container_no:
            opening_domain.append(('move_line_ids.lot_id.name', 'ilike', self.container_no))
        if self.product_id:
            opening_domain.append(('move_line_ids.product_id', '=', self.product_id.id))
        
        opening_stock_moves = self.env['stock.move'].search(opening_domain)
        
        # Calculate opening quantities
        opening_quantities = {}
        for move_line in opening_stock_moves.mapped('move_line_ids'):
            raw_container = (move_line.lot_id.name or '').strip() or 'Unknown'
            #container_id = raw_container.split('-', 1)[1].strip() if '-' in raw_container else raw_container
            container_id = self.get_container_str(raw_container)
            product = move_line.product_id
            key = (container_id, product.id)

            if key not in opening_quantities:
                opening_quantities[key] = 0.0

            # Calculate net movement for opening balance
            if move_line.location_dest_id.usage == 'internal' and move_line.location_id.usage == 'supplier':
                opening_quantities[key] += move_line.quantity or 0.0
            elif move_line.location_id.usage == 'internal' and move_line.location_dest_id.usage == 'customer':
                opening_quantities[key] -= move_line.quantity or 0.0

        # 2. Get movements during the report period
        period_domain = [
            ('picking_id.date_done', '>=', from_date_str),
            ('picking_id.date_done', '<=', to_date_str),
            ('state', '=', 'done'),
            ('product_id.categ_id', '=', category_id),
        ]
        if self.container_no:
            period_domain.append(('move_line_ids.lot_id.name', 'ilike', self.container_no))
        if self.product_id:
            period_domain.append(('product_id', '=', self.product_id.id))
        
        period_stock_moves = self.env['stock.move'].search(period_domain)

        # Track all products with movement during report period
        all_period_products = set()
        
        # Process period movements
        for move_line in period_stock_moves.mapped('move_line_ids'):
            raw_container = (move_line.lot_id.name or '').strip() or 'Unknown'
            #container_id = raw_container.split('-', 1)[1].strip() if '-' in raw_container else raw_container
            container_id = self.get_container_str(raw_container)
            product = move_line.product_id
            key = (container_id, product.id)
            
            # Record all products with movement during report period
            all_period_products.add(key)
            
            if key not in temp_data:
                # Initialize with opening quantity (0 if not found)
                opening_qty = opening_quantities.get(key, 0.0)
                temp_data[key] = {
                    'opening_quantity': opening_qty,
                    'inbound_quantity': 0.0,
                    'outbound_quantity': 0.0,
                    'onhand_quantity': opening_qty,  # Start with opening balance
                }

            # Calculate period movements
            if move_line.location_dest_id.usage == 'internal' and move_line.location_id.usage == 'supplier':
                temp_data[key]['inbound_quantity'] += move_line.quantity or 0.0
                temp_data[key]['onhand_quantity'] += move_line.quantity or 0.0
            elif move_line.location_id.usage == 'internal' and move_line.location_dest_id.usage == 'customer':
                temp_data[key]['outbound_quantity'] += move_line.quantity or 0.0
                temp_data[key]['onhand_quantity'] -= move_line.quantity or 0.0

        # 3. Handle products with opening quantities but no period movements
        for (container_id, product_id), opening_qty in opening_quantities.items():
            if (container_id, product_id) not in temp_data and opening_qty != 0:
                temp_data[(container_id, product_id)] = {
                    'opening_quantity': opening_qty,
                    'inbound_quantity': 0.0,
                    'outbound_quantity': 0.0,
                    'onhand_quantity': opening_qty,
                }

        # 4. Handle products with period movements but no opening quantities
        for key in all_period_products:
            if key not in temp_data:
                # This product has movement during period but no opening stock record
                # Create record with 0 opening quantity
                temp_data[key] = {
                    'opening_quantity': 0.0,
                    'inbound_quantity': 0.0,
                    'outbound_quantity': 0.0,
                    'onhand_quantity': 0.0,
                }
                
                # Re-process all movement records for this product to calculate period quantities
                container_id, product_id = key
                for move_line in period_stock_moves.mapped('move_line_ids'):
                    raw_container = (move_line.lot_id.name or '').strip() or 'Unknown'
                    #line_container_id = raw_container.split('-', 1)[1].strip() if '-' in raw_container else raw_container
                    line_container_id = self.get_container_str(raw_container)
                    line_product_id = move_line.product_id.id
                    
                    if (line_container_id, line_product_id) == key:
                        if move_line.location_dest_id.usage == 'internal' and move_line.location_id.usage == 'supplier':
                            temp_data[key]['inbound_quantity'] += move_line.quantity or 0.0
                            temp_data[key]['onhand_quantity'] += move_line.quantity or 0.0
                        elif move_line.location_id.usage == 'internal' and move_line.location_dest_id.usage == 'customer':
                            temp_data[key]['outbound_quantity'] += move_line.quantity or 0.0
                            temp_data[key]['onhand_quantity'] -= move_line.quantity or 0.0

        # Prepare final records (batch create for performance)
        create_lines = []
        
        for (container_id, product_id), quantities in temp_data.items():
            product = self.env['product.product'].browse(product_id)
            create_lines.append({
                'report_id': self.id,
                'container_no': container_id,
                'product_id': product_id,
                'product_uom_id': product.uom_id.id if product and product.uom_id else False,
                'product_barcode': product.barcode if product else '',
                'opening_quantity': quantities['opening_quantity'],
                'inbound_quantity': quantities['inbound_quantity'],
                'outbound_quantity': quantities['outbound_quantity'],
                'onhand_quantity': quantities['onhand_quantity'],
            })

        if create_lines:
            # Batch create for performance
            self.env['world.depot.store.report.linglong.products'].create(create_lines)
        
        _logger.info("Created %d inventory report lines", len(create_lines))
        
    def action_get_products_data(self):
        """
        UI callable method to refresh this report's product lines.
        Called from a form view button (type="object").
        """
        for rec in self:
            rec._get_products_data()
        
        # Return action to show notification and suggest page reload
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Report Generated'),
                'message': _('Inventory report has been generated successfully. Please refresh the page to see the updated data.'),
                'sticky': False,
                'type': 'success',
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': self._name,
                    'view_mode': 'form',
                    'res_id': self.id,
                    'views': [(False, 'form')],
                    'target': 'current',
                }
            }
        }

    def action_open_products(self):
        """Return an action that opens the product lines for this report."""
        self.ensure_one()
        action = {
            'name': 'Report Products',
            'type': 'ir.actions.act_window',
            'res_model': 'world.depot.store.report.linglong.products',
            'view_mode': 'list',
            'domain': [('report_id', '=', self.id)],
            'context': {'default_report_id': self.id},
        }
        return action
    
    def get_container_str(self, container_no):
        """Extract and return the meaningful part of the container number."""
        parts=container_no.split('-')
        if len(parts)>=2:
            return parts[1].strip() # Return the part after the first hyphen
        else:
            return container_no.strip()
        
        
class MyStockReportLinglongProducts(models.Model):
    _name = 'world.depot.store.report.linglong.products'
    _description = 'Stock Report Products for Linglong'
    
    report_id = fields.Many2one('world.depot.store.report.linglong', string='Report Reference', required=True, ondelete='cascade')
    container_no = fields.Char(string='Container No')
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure', readonly=True) 
    product_id = fields.Many2one('product.product', string='Product', required=True)
    product_barcode = fields.Char(string='Product Barcode')
    opening_quantity = fields.Float(string='Opening Quantity', default=0.0)
    inbound_quantity = fields.Float(string='Inbound Quantity', default=0.0)
    outbound_quantity = fields.Float(string='Outbound Quantity', default=0.0)
    onhand_quantity = fields.Float(string='On-hand Quantity', default=0.0)    