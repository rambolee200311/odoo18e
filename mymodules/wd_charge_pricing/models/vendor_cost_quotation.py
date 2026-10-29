# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .charge_item import OPERATION_TYPE


class VendorCostQuotation(models.Model):
    _name = "vendor.cost.quotation"
    _description = "Vendor Cost Quotation"
    _order = "id desc"

    name = fields.Char(string="Quotation Name", required=True, index=True)
    currency_id = fields.Many2one("res.currency", string="Currency", required=True, default=lambda self: self.env.company.currency_id.id)
    state = fields.Selection([("draft", "Draft"), ("active", "Active")], string="Status", default="draft", readonly=True, index=True)
    remark = fields.Text(string="Remark")
    line_ids = fields.One2many("vendor.cost.quotation.line", "quotation_id", string="Cost Lines", copy=True)
    handover_line_ids = fields.One2many("vendor.cost.quotation.line", "quotation_id", string="Handover Cost Lines", domain=[("operation_type", "=", "handover")], copy=True)
    clearance_line_ids = fields.One2many("vendor.cost.quotation.line", "quotation_id", string="Clearance Cost Lines", domain=[("operation_type", "=", "clearance")], copy=True)

    def action_set_active(self):
        for rec in self:
            if not rec.line_ids:
                raise ValidationError(_("Vendor cost quotation must have at least one cost line before activation."))
            rec.write({"state": "active"})
        return True

    def action_set_draft(self):
        for rec in self:
            rec.write({"state": "draft"})
        return True


class VendorCostQuotationLine(models.Model):
    _name = "vendor.cost.quotation.line"
    _description = "Vendor Cost Quotation Line"
    _order = "id desc"

    quotation_id = fields.Many2one("vendor.cost.quotation", string="Vendor Cost Quotation", required=True, ondelete="cascade", index=True)
    operation_type = fields.Selection(OPERATION_TYPE, string="Operation Type", required=True, default="handover", index=True)
    charge_item_id = fields.Many2one("world.depot.charge.item", string="Charge Item", required=True, ondelete="restrict", index=True)
    qty = fields.Float(string="Qty", required=True, default=1.0)
    unit_price = fields.Monetary(string="Unit Price", required=True, default=0.0)
    is_fixed_fee = fields.Boolean(string="Fixed Fee", default=False)
    create_receivable = fields.Boolean(string="Create Receivable", default=False)
    currency_id = fields.Many2one("res.currency", string="Currency", related="quotation_id.currency_id", store=True, readonly=True)
    remark = fields.Char(string="Remark")

    _sql_constraints = [("vendor_cost_quotation_line_unique", "unique(quotation_id, charge_item_id, operation_type)", "Charge item already exists in this vendor cost quotation operation.")]

    @api.constrains("quotation_id", "charge_item_id", "operation_type")
    def check_charge_item_duplicate(self):
        env_vendor_cost_line = self.env["vendor.cost.quotation.line"]
        for rec in self:
            if not rec.quotation_id or not rec.charge_item_id or not rec.operation_type:
                continue
            duplicate_count = env_vendor_cost_line.sudo().search_count([("quotation_id", "=", rec.quotation_id.id), ("charge_item_id", "=", rec.charge_item_id.id), ("operation_type", "=", rec.operation_type), ("id", "!=", rec.id)])
            if duplicate_count:
                raise ValidationError(_("Charge item already exists in this vendor cost quotation operation."))
