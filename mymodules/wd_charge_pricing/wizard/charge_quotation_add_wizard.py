# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.wd_charge_pricing.models.charge_item import OPERATION_TYPE


class ChargeQuotationAddWizard(models.TransientModel):
    _name = "charge.quotation.add.wizard"
    _description = "Charge Quotation Add Wizard"

    quotation_id = fields.Many2one("charge.quotation", string="Quotation", required=True, readonly=True)
    tab_category = fields.Selection(OPERATION_TYPE, string="Tab Category", required=True, index=True)
    currency_id = fields.Many2one("res.currency", string="Currency", related="quotation_id.currency_id", store=True, readonly=True)
    wizard_lines = fields.One2many("charge.quotation.add.wizard.line", "wizard_id", string="Wizard Lines")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        quotation_id = self.env.context.get("default_quotation_id")
        if quotation_id:
            quotation = self.env["charge.quotation"].sudo().browse(quotation_id).exists()
            values["currency_id"] = quotation.currency_id.id
        return values

    def action_confirm(self):
        for rec in self:
            if rec.quotation_id.state != "draft":
                raise ValidationError(_("Only draft quotations can add charge items."))
            selected_item_ids = rec.wizard_lines.mapped("charge_item_id").ids
            if len(selected_item_ids) != len(set(selected_item_ids)):
                raise ValidationError(_("The same charge item cannot be added more than once."))
            env_quotation_line = self.env["charge.quotation.line"]
            existing_lines = env_quotation_line.sudo().search([("quotation_id", "=", rec.quotation_id.id), ("tab_category", "=", rec.tab_category), ("charge_item_id", "in", selected_item_ids)])
            if existing_lines:
                raise ValidationError(_("These charge items already exist in the quotation: %s") % ", ".join(existing_lines.mapped("charge_item_id.display_name")))
            values_list = [{"quotation_id": rec.quotation_id.id, "charge_item_id": line.charge_item_id.id, "tab_category": rec.tab_category, "is_fixed_fee": line.is_fixed_fee, "unit_price": line.unit_price, "remark": line.remark} for line in rec.wizard_lines]
            if values_list:
                env_quotation_line.create(values_list)
        return {"type": "ir.actions.act_window_close"}


class ChargeQuotationAddWizardLine(models.TransientModel):
    _name = "charge.quotation.add.wizard.line"
    _description = "Charge Quotation Add Wizard Line"

    wizard_id = fields.Many2one("charge.quotation.add.wizard", string="Wizard", required=True, ondelete="cascade")
    charge_item_id = fields.Many2one("world.depot.charge.item", string="Charge Item", required=True, ondelete="restrict")
    is_fixed_fee = fields.Boolean(string="Fixed Fee", default=False)
    unit_price = fields.Monetary(string="Unit Price", default=0.0, currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", related="wizard_id.currency_id", store=True, readonly=True)
    remark = fields.Text(string="Remark")
