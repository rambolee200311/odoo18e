from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging
_logger = logging.getLogger(__name__)

class AccountMoveInherit(models.Model):
    _inherit = "account.move"

    bank_proof_attachment_ids = fields.Many2many(
        "ir.attachment",
        "account_move_bank_proof_attachment_rel",
        "move_id",
        "attachment_id",
        string="Bank Proof Attachments",
        copy=False,
        tracking=True,
    )

    def action_confirm_paid_sync_handover(self):
        for move in self:
            if move.move_type != "in_invoice":
                raise ValidationError(_("Only vendor bills can be confirmed."))
            if move.state != "posted":
                raise ValidationError(_("Vendor bill must be posted first."))
            if move.payment_state != "paid":
                raise ValidationError(_("Vendor bill is not fully paid."))
            if not move.bank_proof_attachment_ids:
                raise ValidationError(_("Bank proof (water slip) is required."))

            invoice_line = self.env["operation.order.handover.invoice.line"].search([
                ("vendor_invoice_id", "=", move.id),
                ("payment_mode", "=", "advance"),
            ], limit=1)
            if not invoice_line:
                raise ValidationError(_("No related handover invoice line found."))
            _logger.info(
                "[Handover Sync] Found handover invoice line %s for bill %s",
                invoice_line.id, move.id
            )
            now = fields.Datetime.now()

            if invoice_line.payment_state != "paid":
                invoice_line.write({
                    "payment_state": "paid",
                    "paid_user_id": self.env.user.id,
                    "paid_time": now,
                })

            new_attach_ids = []
            for att in move.bank_proof_attachment_ids:
                new_att = att.copy({
                    "res_model": "operation.order.handover.invoice.line",
                    "res_id": invoice_line.id,
                })
                new_attach_ids.append(new_att.id)

            if new_attach_ids:
                invoice_line.write({
                    "bank_proof_attachment_ids": [(4, i) for i in new_attach_ids]
                })
                _logger.info(
                    "[Handover Sync] Linked %s bank proof attachments to handover invoice line %s",
                    len(new_attach_ids), invoice_line.id
                )

            invoice_line.mapped("handover_id").action_recompute_state()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Payment Paid"),
                "message": _("Payment Paid has been submitted successfully."),
                "type": "success",
                "sticky": False,
            },
        }
