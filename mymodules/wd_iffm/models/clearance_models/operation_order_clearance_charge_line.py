from odoo import api, fields, models, _
from odoo.addons.wd_iffm.models.charge_item_inherit import TAB_CATEGORY_LIST, OPERATION_TYPE
from odoo.exceptions import ValidationError


class OperationOrderClearanceChargeLine(models.Model):
    _name = "operation.order.clearance.charge.line"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Clearance Charge Line (AR)"
    _order = "id desc"

    clearance_id = fields.Many2one("operation.order.clearance", string="Clearance", required=True, ondelete="cascade", index=True)

    container_qty = fields.Integer(string="Container Qty", compute="compute_container_qty", store=True)

    @api.depends("clearance_id.container_qty")
    def compute_container_qty(self):
        for rec in self:
            rec.container_qty = rec.clearance_id.container_qty if rec.clearance_id else 0

    charge_origin_type = fields.Selection([("quotation", "Quotation"), ("manual", "Manual")], string="Charge Source", default="manual", required=True, index=True)

    quotation_id = fields.Many2one("charge.quotation", string="Quotation", related="clearance_id.waybill_id.quotation_id", store=True, readonly=True, index=True)
    project_id = fields.Many2one("project.project", string="Project/Customer", related="clearance_id.project_id", store=True, readonly=True, index=True)
    currency_id = fields.Many2one("res.currency", string="Currency", related="clearance_id.waybill_id.quotation_id.currency_id", store=True, readonly=True, index=True)

    charge_item_id = fields.Many2one("world.depot.charge.item", string="Charge Item", tracking=True)
    quotation_tab_category = fields.Selection(TAB_CATEGORY_LIST, related="charge_item_id.tab_category", string="Tab Category", tracking=True)
    charge_item_operation_type = fields.Selection(OPERATION_TYPE, string="Operation Type", related="charge_item_id.operation_type", store=True, index=True)
    is_fixed_fee = fields.Boolean(string="Fixed Fee", default=False, index=True)
    qty = fields.Integer(string="Qty", default=1.0, tracking=True)
    charge_qty = fields.Integer(string="Charge Quantity", compute="compute_charge_qty", store=True)

    unit_price = fields.Monetary(string="Unit Price", currency_field="currency_id", default=0.0, tracking=True)
    amount_total = fields.Monetary(string="Total Amount", currency_field="currency_id", compute="compute_amount_total", store=True)

    unit_id = fields.Many2one("world.depot.charge.unit", string="Unit", related="charge_item_id.unit_id", store=True)
    manual_amount_total = fields.Monetary(string="Manual Total Amount", currency_field="currency_id", default=0.0, tracking=True)

    remark = fields.Char(string="Remark")

    @api.depends('clearance_id.container_qty', 'clearance_id.hs_code_qty','charge_item_id','charge_item_id.charge_based_on_max')
    def compute_charge_qty(self):
        for rec in self:
            if not rec.charge_item_id.charge_based_on_max:
                rec.charge_qty = 0
                continue
            if rec.clearance_id.container_qty > rec.clearance_id.hs_code_qty:
                rec.charge_qty = rec.clearance_id.container_qty
            else:
                rec.charge_qty = rec.clearance_id.hs_code_qty

    @api.onchange("charge_item_id", "charge_qty", "is_fixed_fee")
    def onchange_charge_qty(self):
        for rec in self:
            if rec.is_fixed_fee:
                rec.qty = 1.0
                continue
            if rec.charge_item_id.charge_based_on_max:
                rec.qty = rec.charge_qty
                #rec.qty = rec.charge_qty or 1.0

    @api.depends("qty", "unit_price",'charge_item_id', "is_fixed_fee")
    def compute_amount_total(self):
        for rec in self:
            if rec.is_fixed_fee:
                rec.amount_total = rec.unit_price or 0.0
                continue
            if rec.charge_item_id.charge_based_on_max:
                rec.amount_total = ((rec.qty or 0) - 1) * (rec.unit_price or 0.0)
                rec.remark = "Maximum charge (qty-1)*unit price"
            else:
                rec.amount_total = (rec.qty or 0.0) * (rec.unit_price or 0.0)

    @api.onchange("charge_item_id")
    def onchange_charge_item_id(self):
        for rec in self:
            if not rec.charge_item_id or not rec.clearance_id:
                continue
            all_lines = rec.clearance_id.charge_line_ids
            other_lines = []
            for line in all_lines:
                if rec.id and line.id:
                    if line.id != rec.id:
                        other_lines.append(line)
                else:
                    if line != rec:
                        other_lines.append(line)
            for line in other_lines:
                if line.charge_item_id and line.charge_item_id.id == rec.charge_item_id.id:
                    raise ValidationError(_("Charge item already exists in this clearance."))
