from odoo import models, fields


class OutboundOrderSummary(models.Model):
    _name = 'world.depot.outbound.order.summary'
    _description = 'Outbound Order Summary'
    _order = 'order_id,product_detail_id'

    order_id = fields.Many2one('world.depot.outbound.order', string='Outbound Order', readonly=True)
    type = fields.Char(string='Type', readonly=True)
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
        # Clear existing data
        self.env.cr.execute(f"DELETE FROM {self._table}")

        # Fetch confirmed outbound orders with stock picking
        outbound_orders = self.env['world.depot.outbound.order'].search([
            ('state', '=', 'confirm'),
            ('picking_PICK', '!=', False)
        ])

        # Populate the summary table
        for order in outbound_orders:
            for pallet in order.outbound_order_product_ids:
                self.create({
                    'order_id': order.id,
                    'type': order.type,
                    'reference': order.reference,
                    'p_date': order.p_date,
                    'project': order.project.id,
                    'unload_company': order.unload_company.id,
                    'delivery_method': order.delivery_method,
                    'load_ref': order.load_ref,
                    'product_detail_id': pallet.id,
                    'product_id': pallet.product_id.id,
                    'product_name': pallet.product_id.name,
                    'quantity': pallet.quantity,
                    'pallet_prefix_code': pallet.pallet_prefix_code,
                })
