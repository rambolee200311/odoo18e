from odoo import fields, models


class OperationBlockingReason(models.Model):
    _name = "operation.blocking.reason"
    _description = "Operation Blocking Reason"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    _rec_name = "short_name"

    name = fields.Char(string="Reason (ZH)", required=True, index=True)
    short_name = fields.Char(string="Short Name", required=True, index=True)

