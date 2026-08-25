# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ProjectProject(models.Model):
    _inherit = "project.project"

    portal_stock_location_line_ids = fields.Many2many("stock.location", "project_portal_stock_location_rel", "project_id", "location_id", string="Portal Stock Locations", copy=False)

    @api.onchange("portal_stock_location_line_ids")
    def onchange_portal_stock_location_line_ids(self):
        for rec in self:
            invalid_locations = rec.portal_stock_location_line_ids.filtered(lambda location: "LOODS" not in (location.name or "").upper())
            if invalid_locations:
                return {
                    "warning": {
                        "title": "Please confirm portal stock locations",
                        "message": "Select a warehouse-zone root location such as LOODS06. This warning does not prevent saving.",
                    },
                }
