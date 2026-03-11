# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OperationOrderHandoverAttachmentLine(models.Model):
    _name = "operation.order.handover.attachment.line"
    _description = "Handover Attachment Line"
    _order = "id desc"

    handover_id = fields.Many2one("operation.order.handover", string="Handover", required=True, ondelete="cascade", index=True)
    doc_type = fields.Selection([("bl", "BL"), ("poa", "POA"),
                                 ("do", "DO/Telex Release"),
                                ("other", "Other")], string="Document Type", required=True, index=True)
    name = fields.Char(string="Document Name")
    file = fields.Binary(string='File')
    remark = fields.Text(string="Remark")
    upload_user_id = fields.Many2one("res.users", string="Uploaded By", readonly=True)
    upload_time = fields.Datetime(string="Uploaded At", readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        now = fields.Datetime.now()
        for rec in records:
            rec.write({"upload_user_id": self.env.user.id, "upload_time": now})
        return records
