from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OperationOrderClearanceCostLine(models.Model):
    _name = "operation.order.clearance.cost.line"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Clearance Cost Line (AP Cost)"
    _order = "id desc"

    clearance_id = fields.Many2one("operation.order.clearance", string="Clearance",related="invoice_line_id.clearance_id", store=True, index=True)

    invoice_line_id = fields.Many2one("operation.order.clearance.invoice.line", string="Related Vendor Ticket", ondelete="set null", index=True)
    cost_nature = fields.Selection(
        [('at cost', 'At Cost'), ('real cost', 'Real Cost')],
        string='Cost Nature',
        default='at cost',
        index=True,
    )
    charge_type = fields.Selection([("quotation", "Quotation"), ("manual", "Manual")], string="Charge Source", default="manual", required=True, index=True)

    currency_id = fields.Many2one("res.currency", string="Currency",related='invoice_line_id.currency_id')

    charge_item_id = fields.Many2one("world.depot.charge.item", string="Charge Item", tracking=True, index=True)
    unit_price = fields.Monetary(string="Unit Price", currency_field="currency_id", default=0.0, tracking=True)
    qty = fields.Float(string="Qty", default=1.0, tracking=True)
    unit_id = fields.Many2one("world.depot.charge.unit", string="Unit", related="charge_item_id.unit_id", store=True)

    amount_total = fields.Monetary(string="Total Amount", currency_field="currency_id", compute="compute_amount_total", store=True)

    is_manual_amount = fields.Boolean(string="Manual Override", tracking=True)
    manual_amount_total = fields.Monetary(string="Manual Total Amount", currency_field="currency_id", default=0.0, tracking=True)

    rule_snapshot = fields.Text(string="Rule Snapshot")
    source_snapshot = fields.Text(string="Source Snapshot")
    remark = fields.Char(string="Remark")

    @api.onchange("invoice_line_id")
    def onchange_cost_invoice(self):
        if self.invoice_line_id:
            self.currency_id = self.invoice_line_id.currency_id

    @api.depends("qty", "unit_price", "is_manual_amount", "manual_amount_total", "clearance_id.state")
    def compute_amount_total(self):
        for rec in self:
            if rec.clearance_id and rec.clearance_id.state == "close":
                continue
            if rec.is_manual_amount:
                rec.amount_total = rec.manual_amount_total or 0.0
            else:
                rec.amount_total = (rec.qty or 0.0) * (rec.unit_price or 0.0)

    @api.onchange("charge_item_id")
    def onchange_charge_item_id(self):
        for rec in self:
            if not rec.charge_item_id or not rec.invoice_line_id:
                continue
            all_lines = rec.invoice_line_id.cost_line_ids
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
                    raise ValidationError(_("Charge item already exists in this invoice."))