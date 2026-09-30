# -*- coding: utf-8 -*-

from odoo import fields, models


class StockQuantPackage(models.Model):
    _inherit = "stock.quant.package"

    blind_stock_count_generation_type = fields.Selection([("normal", "Normal"), ("batch_generated", "Batch Generated")], string="Blind Stock Count Generation Type", default="normal", readonly=True, copy=False, index=True)
