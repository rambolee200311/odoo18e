from odoo import models, fields


class OutboundOrderSNDetail(models.Model):
    _name = 'world.depot.outbound.order.sn.detail'
    _description = 'Outbound Order SN Detail'
    _order = 'order_id,product_id'

    order_id = fields.Many2one('world.depot.outbound.order', string='Outbound Order', readonly=True)
    type = fields.Char(string='Type', readonly=True)
    reference = fields.Char(string='Outbound Reference', readonly=True)
    p_date = fields.Date(string='Date', readonly=True)
    project = fields.Many2one('project.project', string='Project', readonly=True)
    project_name = fields.Char(string='Project Name', readonly=True, related='project.name')
    picking_PICK = fields.Many2one('stock.picking', string='Picking', readonly=True)
    product_id = fields.Many2one('product.product', string='Product')
    product_name = fields.Char(string='Product Name', readonly=True)
    lot_id = fields.Many2one('stock.lot', string='Serial/Lot ID', readonly=True)
    lot_name = fields.Char(string='Serial/Lot Name', readonly=True)
    quantity = fields.Float(string='Quantity', readonly=True)

    def init(self):
        # Clear existing data
        self.env.cr.execute(f"DELETE FROM {self._table}")

        # Fetch confirmed outbound orders with stock picking
        outbound_orders = self.env['world.depot.outbound.order'].search([
            ('state', '=', 'confirm'),
            ('picking_PICK', '!=', False),
        ])
        for order in outbound_orders:
            # For each outbound order, get the related stock picking
            picking = order.picking_PICK
            if picking.state == 'done':
                for move in picking.move_ids:
                    # For each move line in the picking, create a summary record
                    for move_line in move.move_line_ids:
                        self.create({
                            'order_id': order.id,
                            'type': order.type,
                            'reference': order.reference,
                            'p_date': picking.date_done,
                            'project': order.project.id,
                            'picking_PICK': picking.id,
                            'product_id': move_line.product_id.id,
                            'product_name': move_line.product_id.name,
                            'lot_id': move_line.lot_id.id,
                            'lot_name': move_line.lot_id.name,
                            'quantity': move_line.qty_done,
                        })




