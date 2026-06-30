# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.addons.wd_iffm.models.charge_item_inherit  import TAB_CATEGORY_LIST

class ChargeQuotationAddWizard(models.TransientModel):
    _name = "charge.quotation.add.wizard"
    _description = "Charge Quotation Add Wizard"

    quotation_id = fields.Many2one("charge.quotation", string="Quotation", required=True, readonly=True)
    tab_category = fields.Selection(
        TAB_CATEGORY_LIST,
        string="Tab Category",
        required=True,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="quotation_id.currency_id",store=True
    )
    wizard_lines = fields.One2many("charge.quotation.add.wizard.line", "wizard_id", string="Wizard Lines")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        quotation_id = self.env.context.get("default_quotation_id")
        if quotation_id:
            quotation = self.env["charge.quotation"].browse(quotation_id)
            res["currency_id"] = quotation.currency_id.id
        return res

    def action_confirm(self):
        for rec in self:
            lines_to_create = []
            for line in rec.wizard_lines:
                lines_to_create.append({
                    "quotation_id": rec.quotation_id.id,
                    "charge_item_id": line.charge_item_id.id,
                    "is_fixed_fee": line.is_fixed_fee,
                    "unit_price": line.unit_price,
                    "remark": line.remark,
                })
            if lines_to_create:
                self.env["charge.quotation.line"].create(lines_to_create)
        return {"type": "ir.actions.act_window_close"}


class ChargeQuotationAddWizardLine(models.TransientModel):
    _name = "charge.quotation.add.wizard.line"
    _description = "Charge Quotation Add Wizard Line"

    wizard_id = fields.Many2one("charge.quotation.add.wizard", string="Wizard", required=True, ondelete="cascade")
    charge_item_id = fields.Many2one(
        "world.depot.charge.item",
        string="Charge Item",
        required=True,
    )
    is_fixed_fee = fields.Boolean(string="Fixed Fee", default=False)
    unit_price = fields.Monetary(string="Unit Price", default=0.0, currency_field="currency_id")
    currency_id = fields.Many2one(related="wizard_id.currency_id", store=True, readonly=True)

    remark = fields.Text(string="Remark")
