# -*- coding: utf-8 -*-

from odoo import fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    inbound_order_product_pallet_id = fields.Many2one("world.depot.inbound.order.products.pallet", string="Inbound Product Detail", copy=False, index=True, ondelete="restrict")
