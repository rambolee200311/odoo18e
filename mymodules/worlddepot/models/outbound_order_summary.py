from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class OutboundOrderSummary(models.Model):
    _name = 'world.depot.outbound.order.summary'
    _description = 'Outbound Order Summary'
    _order = 'order_id,product_detail_id'

    order_id = fields.Many2one('world.depot.outbound.order', string='Outbound Order', readonly=True)
    type = fields.Char(string='Type', readonly=True)
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

    def init(self):
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