from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
class OperationOrderHandoverCostLine(models.Model):
    _name = "operation.order.handover.cost.line"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Handover Cost Line (AP Cost)"
    _order = "id desc"

    # operation
    handover_id = fields.Many2one("operation.order.handover", string="Handover", required=True, ondelete="cascade", index=True)

    invoice_line_id = fields.Many2one("operation.order.handover.invoice.line", string="Related Vendor Ticket", ondelete="set null", index=True)
    charge_type = fields.Selection([("quotation", "Quotation"), ("manual", "Manual")], string="Charge Source",
                                   default="manual", required=True)

    project_id = fields.Many2one("project.project", string="Project/Customer", related="handover_id.project_id", store=True, readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency", related="handover_id.currency_id", readonly=True,store= True)

    charge_item_id = fields.Many2one("world.depot.charge.item", string="Charge Item", tracking=True)
    unit_price = fields.Monetary(string="Unit Price", currency_field="currency_id", default=0.0, tracking=True)
    qty = fields.Float(string="Qty", default=1.0, tracking=True)
    unit_id = fields.Many2one("world.depot.charge.unit", string="Unit", related="charge_item_id.unit_id", store=True)
    amount_total = fields.Monetary(string="Total Amount", currency_field="currency_id")

    is_manual_amount = fields.Boolean(string="Manual Override", tracking=True)
    rule_snapshot = fields.Text(string="Rule Snapshot")
    source_snapshot = fields.Text(string="Source Snapshot")
    remark = fields.Char(string="Remark")
