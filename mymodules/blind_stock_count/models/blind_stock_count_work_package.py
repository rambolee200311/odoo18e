# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class BlindStockCountWorkPackage(models.Model):
    _name = "blind.stock.count.work.package"
    _inherit = ["mail.thread"]
    _description = "Blind Stock Count Work Package"

    _order = "id desc"

    name = fields.Char(string="Work Package", required=True, copy=False, index=True)
    category_id = fields.Many2one("product.category", string="Product Category", required=True, copy=False, index=True,tracking=True)
    location_line_ids = fields.Many2many("stock.location", "blind_stock_count_work_package_location_rel", "work_package_id", "location_id",tracking=True, string="Location Scope", copy=False)
    count_lines = fields.One2many("blind.stock.count", "work_package_id", string="Blind Stock Counts", copy=False)
    note = fields.Text(string="Notes", copy=False)

    @api.constrains("location_line_ids")
    def check_location_scope(self):
        for rec in self:
            if rec.location_line_ids.filtered(lambda location: location.usage != "internal"):
                raise ValidationError(_("Work package locations must be internal locations."))
