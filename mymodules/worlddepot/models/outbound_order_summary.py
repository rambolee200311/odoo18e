from odoo import models, fields,api
import logging

_logger = logging.getLogger(__name__)


class OutboundOrderSummary(models.Model):
    _name = 'world.depot.outbound.order.summary'
    _description = 'Outbound Order Summary'
    _order = 'order_id,product_detail_id'

    order_id = fields.Many2one('world.depot.outbound.order', string='Outbound Order', readonly=True)
    type = fields.Char(string='Type', readonly=True)
    #type = fields.Char(string='Type', readonly=True, related='order_id.type')  # Add related
    state = fields.Selection(related='order_id.state', string='State', readonly=True)
    reference = fields.Char(string='Outbound Reference', readonly=True)
    p_date = fields.Date(string='Date', readonly=True)
    project = fields.Many2one('project.project', string='Project', readonly=True)
    project_name = fields.Char(string='Project Name', readonly=True, related='project.name')
    unload_company = fields.Many2one('res.partner', string='Unload Company/Person', readonly=True)
    delivery_method = fields.Char(string='Delivery Method', readonly=True)
    load_ref = fields.Char(string='Load Reference', readonly=True)
    product_detail_id = fields.Many2one('world.depot.outbound.order.product', string='Product', readonly=True)
    product_id = fields.Many2one('product.product', string='Product')
    product_name = fields.Char(string='Product Name', readonly=True)
    quantity = fields.Float(string='Quantity', readonly=True)
    pallet_prefix_code = fields.Char(string="Pallet Prefix", readonly=True)

    def init_old(self):
        """Initialize the summary table with data from outbound orders."""
        try:
            # Clear existing data
            self.env.cr.execute(f"DELETE FROM {self._table}")

            # Fetch confirmed outbound orders
            outbound_orders = self.env['world.depot.outbound.order'].search([('state', '!=', 'cancel')])

            # Prepare data for bulk insertion
            summary_data = []
            for order in outbound_orders:
                pallets = self.env['world.depot.outbound.order.product'].search([('outbound_order_id', '=', order.id)])
                for pallet in pallets:
                    if not pallet.product_id:
                        _logger.warning(f"Product missing for pallet line ID {pallet.id} in order ID {order.id}")
                        continue
                    summary_data.append({
                        'order_id': order.id,
                        'type': order.type or '',
                        'state': order.state or '',
                        'reference': order.reference or '',
                        'p_date': order.p_date or False,
                        'project': order.project.id,
                        'unload_company': order.unload_company.id or False,
                        'delivery_method': order.delivery_method or '',
                        'load_ref': order.load_ref or '',
                        'product_detail_id': pallet.id or False,
                        'product_id': pallet.product_id.id or False,
                        'product_name': pallet.product_id.name or '',
                        'quantity': pallet.quantity or 0,
                        'pallet_prefix_code': pallet.pallet_prefix_code or '',
                    })

            # Bulk create records
            if summary_data:
                self.env['world.depot.outbound.order.summary'].create(summary_data)

        except Exception as e:
            _logger.error(f"Error initializing OutboundOrderSummary: {e}")

    def init(self):
        """Initialize the summary table with data from outbound orders."""
        try:
            # Clear existing data
            self.env.cr.execute(f"DELETE FROM {self._table}")

            # Fetch ALL outbound orders (including cancelled if needed)
            domain = [('state', '!=', 'cancel')]
            outbound_orders = self.env['world.depot.outbound.order'].search(domain)
            _logger.info(f"Found {len(outbound_orders)} outbound orders to process")

            summary_data = []
            orders_processed = 0
            orders_with_issues = 0

            for order in outbound_orders:
                orders_processed += 1

                # Check if order has pallets/products
                pallets = self.env['world.depot.outbound.order.product'].search([
                    ('outbound_order_id', '=', order.id)
                ])

                if not pallets:
                    _logger.warning(f"Order {order.id} ({order.reference}) has no pallet lines")
                    orders_with_issues += 1
                    # Consider creating a summary record even for empty orders
                    summary_data.append({
                        'order_id': order.id,
                        'type': order.type or '',
                        'state': order.state or '',
                        'reference': order.reference or '',
                        'p_date': order.p_date,
                        'project': order.project.id if order.project else False,
                        'unload_company': order.unload_company.id if order.unload_company else False,
                        'delivery_method': order.delivery_method or '',
                        'load_ref': order.load_ref or '',
                        'product_detail_id': False,
                        'product_id': False,
                        'product_name': '',
                        'quantity': 0,
                        'pallet_prefix_code': '',
                    })
                    continue

                for pallet in pallets:
                    if not pallet.product_id:
                        _logger.warning(f"Product missing for pallet line ID {pallet.id} in order ID {order.id}")
                        orders_with_issues += 1
                        # Still create record but with empty product info
                        summary_data.append({
                            'order_id': order.id,
                            'type': order.type or '',
                            'state': order.state or '',
                            'reference': order.reference or '',
                            'p_date': order.p_date,
                            'project': order.project.id if order.project else False,
                            'unload_company': order.unload_company.id if order.unload_company else False,
                            'delivery_method': order.delivery_method or '',
                            'load_ref': order.load_ref or '',
                            'product_detail_id': pallet.id,
                            'product_id': False,
                            'product_name': 'MISSING PRODUCT',
                            'quantity': pallet.quantity or 0,
                            'pallet_prefix_code': pallet.pallet_prefix_code or '',
                        })
                        continue

                    summary_data.append({
                        'order_id': order.id,
                        'type': order.type or '',
                        'state': order.state or '',
                        'reference': order.reference or '',
                        'p_date': order.p_date,
                        'project': order.project.id if order.project else False,
                        'unload_company': order.unload_company.id if order.unload_company else False,
                        'delivery_method': order.delivery_method or '',
                        'load_ref': order.load_ref or '',
                        'product_detail_id': pallet.id,
                        'product_id': pallet.product_id.id,
                        'product_name': pallet.product_id.name or '',
                        'quantity': pallet.quantity or 0,
                        'pallet_prefix_code': pallet.pallet_prefix_code or '',
                    })

            _logger.info(f"Processed {orders_processed} orders, {orders_with_issues} had issues")
            _logger.info(f"Creating {len(summary_data)} summary records")

            # Bulk create in batches
            batch_size = 1000
            for i in range(0, len(summary_data), batch_size):
                batch = summary_data[i:i + batch_size]
                try:
                    self.env['world.depot.outbound.order.summary'].create(batch)
                except Exception as batch_error:
                    _logger.error(f"Error creating batch {i // batch_size}: {batch_error}")
                    # Try creating records individually to identify problematic ones
                    for record_data in batch:
                        try:
                            self.env['world.depot.outbound.order.summary'].create([record_data])
                        except Exception as single_error:
                            _logger.error(f"Failed to create record: {record_data}. Error: {single_error}")

        except Exception as e:
            _logger.error(f"Error initializing OutboundOrderSummary: {e}")
            _logger.error("Full traceback:", exc_info=True)
    
        
    @api.model
    def action_manual_refresh(self, *args, **kwargs):
        """Manual entry point to refresh the outbound order summary.

        This can be called from an automated action or server action in Odoo UI.
        It simply rebuilds the summary table by calling the `init` method.
        """
        _logger.info("Manual refresh of OutboundOrderSummary requested")
        try:
            # Rebuild the summary
            self.init()
            _logger.info("Manual refresh completed successfully")
            return True
        except Exception as e:
            _logger.error("Manual refresh failed: %s", e, exc_info=True)
            return False