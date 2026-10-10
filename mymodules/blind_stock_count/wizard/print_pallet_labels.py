# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class BlindStockCountPrintPalletLabels(models.TransientModel):
    _name = "blind.stock.count.print.pallet.labels"
    _description = "Print Blind Stock Count Pallet Labels"

    start_position = fields.Integer(string="Start Position", required=True, default=1)
    end_position = fields.Integer(string="End Position", required=True, default=1)

    def action_print_labels(self):
        package_model = self.env["stock.quant.package"]
        for rec in self:
            if rec.start_position <= 0:
                raise UserError(_("Start position must be greater than zero."))
            if rec.end_position < rec.start_position:
                raise UserError(_("End position must not be less than start position."))
            active_domain = rec.env.context.get("active_domain", [])
            package_count = package_model.sudo().search_count(active_domain)
            if rec.end_position > package_count:
                raise UserError(_("Only %s pallet(s) match the current filters.") % package_count)
            packages = package_model.sudo().search(active_domain, order="id asc", offset=rec.start_position - 1, limit=rec.end_position - rec.start_position + 1)
            return self.env.ref("blind_stock_count.action_report_blind_stock_count_pallet_label").report_action(packages)
        return False
