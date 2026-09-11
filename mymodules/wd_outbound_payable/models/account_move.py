# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    outbound_payable_id = fields.Many2one("world.depot.outbound.order.payable", string="Outbound Payable", ondelete="set null", index=True, copy=False)

    def action_confirm_outbound_payable_paid(self):
        for rec in self:
            if rec.move_type != "in_invoice" or not rec.outbound_payable_id:
                raise ValidationError(_("This action is only available for an outbound payable vendor bill."))
            if rec.payment_info_synced:
                raise ValidationError(_("Payment information has already been synced."))
            if rec.state != "posted" or rec.payment_state != "paid":
                raise ValidationError(_("The vendor bill must be posted and fully paid before confirmation."))
            if not rec.bank_proof_attachment_ids:
                raise ValidationError(_("Bank proof attachments are required before confirmation."))
            payable = rec.outbound_payable_id
            if payable.payment_state != "paying":
                raise ValidationError(_("Only payment-requested outbound payables can be confirmed."))
            attachment_ids = []
            for attachment in rec.bank_proof_attachment_ids:
                copied_attachment = attachment.copy({"res_model": payable._name, "res_id": payable.id})
                attachment_ids.append(copied_attachment.id)
            payable.write({"payment_state": "paid", "bank_proof_attachment_ids": [(6, 0, attachment_ids)], "paid_user_id": self.env.user.id, "paid_datetime": fields.Datetime.now()})
            rec.write({"payment_info_synced": True})
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {"type": "success", "message": _("Outbound payable payment confirmed."), "next": {"type": "ir.actions.client", "tag": "soft_reload"}}}
