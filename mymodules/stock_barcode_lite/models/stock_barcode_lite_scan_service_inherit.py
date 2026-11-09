# -*- coding: utf-8 -*-

from odoo import api, models


class StockBarcodeLiteScanService(models.AbstractModel):
    _inherit = "stock.barcode.lite.scan.service"

    @api.model
    def get_picking_from_barcode(self, code):
        picking = super().get_picking_from_barcode(code)
        if picking:
            return picking
        inbound_order = self.env["world.depot.inbound.order"].sudo().search([("billno", "=", code)], limit=1)
        return self.env["stock.picking"].sudo().search([
            ("id", "=", inbound_order.stock_picking_id.id),
            ("picking_type_id.code", "=", "incoming"),
            ("state", "!=", "cancel"),
        ], limit=1)
