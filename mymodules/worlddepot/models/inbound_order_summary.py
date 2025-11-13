from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class InboundOrderSummary(models.Model):
    _name = 'world.depot.inbound.order.summary'
    _description = 'Inbound Order Summary'
    _order = 'order_id, pallet_id'

    order_id = fields.Many2one('world.depot.inbound.order', string='Inbound Order', readonly=True)
    type = fields.Selection(related='order_id.type', string='Type', readonly=True)
    a_date = fields.Date(string='Date', readonly=True, related='order_id.a_date')
    state = fields.Selection(related='order_id.state', string='State', readonly=True)
    i_date = fields.Date(string='Inbound Date', readonly=True, related='order_id.i_date')
    i_datetime = fields.Datetime(string='Inbound DateTime', readonly=True, related='order_id.i_datetime')
    project = fields.Many2one('project.project', string='Project', readonly=True)
    project_name = fields.Char(string='Project Name', readonly=True, related='project.name')
    reference = fields.Char(string='Inbound Reference', readonly=True)
    bl_no = fields.Char(string='Bill of Lading', readonly=True)
    cntr_no = fields.Char(string='Container No', readonly=True)
    pallet_id = fields.Many2one('world.depot.inbound.order.product', string='Pallet', readonly=True)
    pallets = fields.Float(string='Pallets', readonly=True)
    mixed = fields.Boolean(string='Mixed', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    product_name = fields.Char(string='Product Name', readonly=True)
    barcode = fields.Char(string='Barcode', readonly=True)
    default_code = fields.Char(string='Internal Reference', readonly=True)
    quantity = fields.Float(string='Pcs/Pallet', readonly=True)
    qty_subtotal = fields.Float(string='Quantity Subtotal', readonly=True)
    stock_picking_id = fields.Many2one('stock.picking', string='Stock Picking', readonly=True)

    def init_old(self):
        """Initialize the summary table with data from inbound orders."""
        try:
            # Clear existing data
            self.env.cr.execute(f"DELETE FROM {self._table}")

            # Fetch confirmed inbound orders
            inbound_orders = self.env['world.depot.inbound.order'].search([('state', '!=', 'cancel')])

            # Prepare data for bulk insertion
            summary_data = []
            for order in inbound_orders:
                pallets = self.env['world.depot.inbound.order.product'].search([('inbound_order_id', '=', order.id)])
                # If no pallets, create a placeholder row so the order is represented
                if not pallets:
                    _logger.warning(f"Order {order.id} ({order.reference}) has no pallets (init_old)")
                    summary_data.append({
                        'order_id': order.id,
                        'state': order.state,
                        'stock_picking_id': order.stock_picking_id.id or False,
                        'a_date': order.a_date,
                        'i_date': order.i_date,
                        'i_datetime': order.i_datetime,
                        'type': order.type,
                        'project': order.project.id if order.project else False,
                        'reference': order.reference,
                        'cntr_no': order.cntr_no or '',
                        'bl_no': order.bl_no or '',
                        'pallet_id': False,
                        'pallets': 0,
                        'mixed': False,
                        'product_id': False,
                        'product_name': 'No pallets',
                        'barcode': '',
                        'default_code': '',
                        'quantity': 0,
                        'qty_subtotal': 0,
                    })
                    continue

                for pallet in pallets:
                    mixed = len(pallet.inbound_order_product_pallet_ids) > 1
                    products = self.env['world.depot.inbound.order.products.pallet'].search(
                        [('inbound_order_product_id', '=', pallet.id)]
                    )

                    # If a pallet has no products, add a placeholder row for the pallet
                    if not products:
                        _logger.warning(f"Pallet {pallet.id} in order {order.id} has no products (init_old)")
                        summary_data.append({
                            'order_id': order.id,
                            'state': order.state,
                            'stock_picking_id': order.stock_picking_id.id or False,
                            'a_date': order.a_date,
                            'i_date': order.i_date,
                            'i_datetime': order.i_datetime,
                            'type': order.type,
                            'project': order.project.id if order.project else False,
                            'reference': order.reference,
                            'cntr_no': order.cntr_no or '',
                            'bl_no': order.bl_no or '',
                            'pallet_id': pallet.id,
                            'pallets': pallet.pallets or 0,
                            'mixed': mixed,
                            'product_id': False,
                            'product_name': 'No products',
                            'barcode': '',
                            'default_code': '',
                            'quantity': 0,
                            'qty_subtotal': 0,
                        })
                        continue

                    for i, product in enumerate(products, start=1):
                        if not product.product_id:
                            _logger.warning(
                                f"Product missing for pallet line ID {product.id} in order ID {order.id}"
                            )
                            continue
                        qty = product.quantity if product.quantity is not None else 0
                        summary_data.append({
                            'order_id': order.id,
                            'state': order.state,
                            'stock_picking_id': order.stock_picking_id.id,
                            'a_date': order.a_date,
                            'i_date': order.i_date,
                            'i_datetime': order.i_datetime,
                            'type': order.type,
                            'project': order.project.id,
                            'reference': order.reference,
                            'cntr_no': order.cntr_no or '',
                            'bl_no': order.bl_no or '',
                            'pallet_id': pallet.id,
                            'pallets': pallet.pallets if i == 1 else 0,
                            'mixed': mixed,
                            'product_id': product.product_id.id,
                            'product_name': product.product_id.name,
                            'barcode': product.product_id.barcode or '',
                            'default_code': product.product_id.default_code or '',
                            'quantity': qty,
                            'qty_subtotal': (pallet.pallets or 1) * qty,
                        })

            # Bulk create records
            if summary_data:
                self.env['world.depot.inbound.order.summary'].create(summary_data)

        except Exception as e:
            _logger.error(f"Error initializing InboundOrderSummary: {e}")

    def init(self):
        """Initialize the summary table with data from inbound orders."""
        try:
            # Clear existing data
            self.env.cr.execute(f"DELETE FROM {self._table}")
            domain = [('state', '!=', 'cancel')]

            # Include ALL orders (remove state filter)
            inbound_orders = self.env['world.depot.inbound.order'].search(domain)

            _logger.info(f"Processing {len(inbound_orders)} inbound orders")

            summary_data = []
            orders_processed = 0
            orders_with_issues = 0

            for order in inbound_orders:
                orders_processed += 1
                pallets = self.env['world.depot.inbound.order.product'].search([
                    ('inbound_order_id', '=', order.id)
                ])

                if not pallets:
                    _logger.warning(f"Order {order.id} ({order.reference}) has no pallets")
                    orders_with_issues += 1
                    # create placeholder for orders without pallets
                    summary_data.append({
                        'order_id': order.id,
                        'state': order.state,
                        'stock_picking_id': order.stock_picking_id.id or False,
                        'a_date': order.a_date,
                        'i_date': order.i_date,
                        'i_datetime': order.i_datetime,
                        'type': order.type,
                        'project': order.project.id if order.project else False,
                        'reference': order.reference,
                        'cntr_no': order.cntr_no or '',
                        'bl_no': order.bl_no or '',
                        'pallet_id': False,
                        'pallets': 0,
                        'mixed': False,
                        'product_id': False,
                        'product_name': 'No pallets',
                        'barcode': '',
                        'default_code': '',
                        'quantity': 0,
                        'qty_subtotal': 0,
                    })
                    continue

                for pallet in pallets:
                    mixed = len(pallet.inbound_order_product_pallet_ids) > 1
                    products = self.env['world.depot.inbound.order.products.pallet'].search([
                        ('inbound_order_product_id', '=', pallet.id)
                    ])

                    if not products:
                        _logger.warning(f"Pallet {pallet.id} in order {order.id} has no products")
                        orders_with_issues += 1
                        # add placeholder for the pallet without products
                        summary_data.append({
                            'order_id': order.id,
                            'state': order.state,
                            'stock_picking_id': order.stock_picking_id.id or False,
                            'a_date': order.a_date,
                            'i_date': order.i_date,
                            'i_datetime': order.i_datetime,
                            'type': order.type,
                            'project': order.project.id if order.project else False,
                            'reference': order.reference,
                            'cntr_no': order.cntr_no or '',
                            'bl_no': order.bl_no or '',
                            'pallet_id': pallet.id,
                            'pallets': pallet.pallets or 0,
                            'mixed': mixed,
                            'product_id': False,
                            'product_name': 'No products',
                            'barcode': '',
                            'default_code': '',
                            'quantity': 0,
                            'qty_subtotal': 0,
                        })
                        continue

                    for i, product in enumerate(products, start=1):
                        if not product.product_id:
                            _logger.warning(
                                f"Product missing for pallet line ID {product.id} in order ID {order.id}"
                            )
                            orders_with_issues += 1
                            continue

                        qty = product.quantity if product.quantity is not None else 0

                        summary_data.append({
                            'order_id': order.id,
                            'state': order.state,
                            'stock_picking_id': order.stock_picking_id.id,
                            'a_date': order.a_date,
                            'i_date': order.i_date,
                            'i_datetime': order.i_datetime,
                            'type': order.type,
                            'project': order.project.id,
                            'reference': order.reference,
                            'cntr_no': order.cntr_no or '',
                            'bl_no': order.bl_no or '',
                            'pallet_id': pallet.id,
                            'pallets': pallet.pallets if i == 1 else 0,
                            'mixed': mixed,
                            'product_id': product.product_id.id,
                            'product_name': product.product_id.name,
                            'barcode': product.product_id.barcode or '',
                            'default_code': product.product_id.default_code or '',
                            'quantity': qty,
                            'qty_subtotal': (pallet.pallets or 1) * qty,
                        })

            _logger.info(f"Processed {orders_processed} orders, {orders_with_issues} had issues")
            _logger.info(f"Creating {len(summary_data)} summary records")

            # Bulk create in batches to avoid memory issues
            batch_size = 1000
            for i in range(0, len(summary_data), batch_size):
                batch = summary_data[i:i + batch_size]
                self.env['world.depot.inbound.order.summary'].create(batch)

            _logger.info("Summary initialization completed successfully")

        except Exception as e:
            _logger.error(f"Error initializing InboundOrderSummary: {e}")
            _logger.error("Full traceback:", exc_info=True)

    @api.model
    def action_manual_refresh(self, *args, **kwargs):
        """Manual entry point to refresh the inbound order summary.

        This can be called from an automated action or server action in Odoo UI.
        It simply rebuilds the summary table by calling the `init` method.
        """
        _logger.info("Manual refresh of InboundOrderSummary requested")
        try:
            # Rebuild the summary
            self.init()
            _logger.info("Manual refresh completed successfully")
            return True
        except Exception as e:
            _logger.error("Manual refresh failed: %s", e, exc_info=True)
            return False