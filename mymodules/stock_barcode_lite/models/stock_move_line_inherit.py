# -*- coding: utf-8 -*-

from odoo import fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    is_location_updated = fields.Boolean(string="Location Updated", default=False, copy=False, index=True)
    location_updated_by_id = fields.Many2one("res.users", string="Location Updated By", copy=False)
    location_updated_datetime = fields.Datetime(string="Location Updated Datetime", copy=False)
