from odoo import models, fields


class InboundOrderSummary(models.Model):
    _name = 'world.depot.inbound.order.summary'
    _description = 'Inbound Order Summary'
    _order = 'order_id,pallet_id'

    order_id = fields.Many2one('world.depot.inbound.order', string='Inbound Order', readonly=True)
    type = fields.Selection(related='order_id.type', string='Type', readonly=True)
    a_date = fields.Date(string='Date', readonly=True, related='order_id.a_date')
    state = fields.Selection(related='order_id.state', string='Type', readonly=True)
    i_date = fields.Date(string='Inbound Date', readonly=True, related='order_id.i_date')
    project = fields.Many2one('project.project', string='Project', readonly=True)
    project_name = fields.Char(string='Project Name', readonly=True, related='project.name')
    reference = fields.Char(string='Inbound Reference', readonly=True)
    bl_no = fields.Char(string='Bill of Lading', readonly=True)
    cntr_no = fields.Char(string='Container No', readonly=True)
    pallet_id = fields.Many2one('world.depot.inbound.order.product', string='Pallet', readonly=True)
    pallets = fields.Float(string='Pallets', readonly=True)
    mixed = fields.Boolean(string='Mixed', readonly=True)
    product_id = fields.Many2one(
        'product.product',
        string='Product'
    )
    product_name = fields.Char(string='Product Name', readonly=True)
    barcode = fields.Char(string='Barcode', readonly=True)
    default_code = fields.Char(string='Internal Reference', readonly=True)
    quantity = fields.Float(string='Pcs/Pallet', readonly=True)
    qty_subtotal = fields.Float(string='Quantity', readonly=True)
    stock_picking_id = fields.Many2one(
        'stock.picking', string='Stock Picking', readonly=True,
        help='Reference to the related Stock Picking'
    )

    def init(self):
        # Clear existing data
        self.env.cr.execute(f"DELETE FROM {self._table}")

        # Fetch confirmed inbound orders with stock picking
        domain=[
            ('state', '!=', 'cancel'),

        ]
        # ('stock_picking_id', '!=', False)

        inbound_orders = self.env['world.depot.inbound.order'].search(domain)

        # Populate the summary table
        for order in inbound_orders:
            for pallet in order.inbound_order_product_ids:
                mixed = False
                if len(pallet.inbound_order_product_pallet_ids) > 1:
                    mixed = True
                i = 1
                for product in pallet.inbound_order_product_pallet_ids:
                    pallets = pallet.pallets
                    if i > 1:
                        pallets = 0
                    self.create({
                        'order_id': order.id,
                        'state': order.state,
                        'stock_picking_id': order.stock_picking_id.id,
                        'a_date': order.a_date,
                        'i_date': order.i_date,
                        'type': order.type,
                        'project': order.project.id,
                        'reference': order.reference,
                        'cntr_no': order.cntr_no,
                        'bl_no': order.bl_no,
                        'pallet_id': pallet.id,
                        'pallets': pallets,
                        'mixed': mixed,
                        'product_id': product.product_id.id,  # Use the product ID
                        'product_name': product.product_id.name,  # Use the product name
                        'barcode': product.product_id.barcode,
                        'default_code': product.product_id.default_code,
                        'quantity': product.quantity,
                        'qty_subtotal': pallet.pallets * product.quantity,
                    })
                    i += 1
