# -*- coding: utf-8 -*-

import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockQuantPackage(models.Model):
    _inherit = "stock.quant.package"
    _sql_constraints = [
        ("barcode_unique", "unique(barcode)", "Barcode must be unique."),
    ]

    billno = fields.Char(string="Bill No", copy=False)
    reference = fields.Char(string="Reference", copy=False)
    cntr_no = fields.Char(string="Container No", copy=False)
    barcode = fields.Char(string="Barcode", copy=False, index=True)

    @api.model
    def generate_sunrise_package_barcode(self):
        """Return an unused eight-character barcode for a Sunrise package."""
        for _attempt in range(20):
            barcode = uuid.uuid4().hex[:8].upper()
            if not self.sudo().search([("barcode", "=", barcode)], limit=1):
                return barcode
        raise UserError(_("Could not generate a unique Sunrise package barcode."))
