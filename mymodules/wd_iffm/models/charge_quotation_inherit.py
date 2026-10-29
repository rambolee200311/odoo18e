# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import ValidationError


class ChargeQuotation(models.Model):
    _inherit = "charge.quotation"

    def write(self, vals):
        if "currency_id" in vals:
            env_waybill = self.env["world.depot.waybill"]
            for rec in self:
                if vals["currency_id"] != rec.currency_id.id and env_waybill.sudo().search_count([("quotation_id", "=", rec.id)], limit=1):
                    raise ValidationError(_("The currency cannot be changed because this quotation is already used by a waybill."))
        return super().write(vals)
