# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request
from odoo.addons.stock_barcode.controllers.stock_barcode import StockBarcodeController


class StockBarcodeLiteController(StockBarcodeController):

    def _try_open_picking(self, barcode):
        picking = request.env["stock.picking"].sudo().search([
            ("name", "=", barcode),
        ], limit=1)
        if picking:
            picking.check_native_barcode_scan_allowed()
        return super()._try_open_picking(barcode)

    @http.route()
    def save_barcode_data(self, model, res_id, write_field, write_vals):
        if model == "stock.picking" and res_id:
            picking = request.env["stock.picking"].sudo().browse(res_id).exists()
            if picking:
                picking.check_native_barcode_scan_allowed()
        return super().save_barcode_data(model, res_id, write_field, write_vals)
