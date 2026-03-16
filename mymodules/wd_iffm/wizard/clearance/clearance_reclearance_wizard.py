from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class ClearanceReclearanceWizard(models.TransientModel):
    _name = "clearance.reclearance.wizard"
    _description = "Clearance Re-Clearance Wizard"

    clearance_id = fields.Many2one("operation.order.clearance", string="Clearance", required=True, readonly=True)
    reason = fields.Text(string="Re-Clearance Reason", required=True)

    def action_confirm(self):
        for rec in self:
            if not rec.reason or not rec.reason.strip():
                raise ValidationError(_("Re-clearance reason is required."))
            if rec.clearance_id.state != "clearancing":
                raise ValidationError(_("Only clearancing order can be re-cleared."))

            new_remark = (rec.clearance_id.remark or "").strip()
            append_text = _("[Re-Clearance] %s") % rec.reason.strip()
            new_remark = f"{new_remark}\n{append_text}" if new_remark else append_text

            rec.clearance_id.write({
                "state": "paid",
                "reclearance_count": rec.clearance_id.reclearance_count + 1,
                "reclearance_reason": rec.reason.strip(),
                "reclearance_user_id": rec.env.user.id,
                "reclearance_time": fields.Datetime.now(),
                "remark": new_remark,
            })
        return {"type": "ir.actions.act_window_close"}
