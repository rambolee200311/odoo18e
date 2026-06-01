# -*- coding: utf-8 -*-

from odoo import fields, models


class StockQuantPackage(models.Model):
    _inherit = "stock.quant.package"

    billno = fields.Char(string="Bill No", copy=False)
    reference = fields.Char(string="Reference", copy=False)
    cntr_no = fields.Char(string="Container No", copy=False)
    barcode = fields.Char(string="Barcode", copy=False, index=True)
