from odoo import api, fields, models, _

class WaybillInherit(models.Model):
    _inherit = "world.depot.waybill"

    quotation_id = fields.Many2one("charge.quotation", string="Quotation", index=True)
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related='quotation_id.currency_id'
    )
    def action_create_handover(self):
        for rec in self:
            rec.env['operation.order.handover'].create({
                'waybill_id': rec.id,
                'project_id': rec.project.id,
                'shipping_line_id': rec.shipping.id,
            })