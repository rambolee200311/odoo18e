# -*- coding: utf-8 -*-

from odoo import _, fields, models


class StockQuantPackage(models.Model):
    _inherit = "stock.quant.package"

    blind_stock_count_generation_type = fields.Selection([("normal", "Normal"), ("batch_generated", "Batch Generated")], string="Blind Stock Count Generation Type", default="normal", readonly=True, copy=False, index=True)

    def action_open_blind_stock_count_print_pallet_labels(self):
        for rec in self:
            active_domain = rec.env.context.get("active_domain", [])
            break
        else:
            active_domain = self.env.context.get("active_domain", [])
        return {"type": "ir.actions.act_window", "name": _("Print Label Range"), "res_model": "blind.stock.count.print.pallet.labels", "view_mode": "form", "target": "new", "context": {"active_domain": active_domain}}
