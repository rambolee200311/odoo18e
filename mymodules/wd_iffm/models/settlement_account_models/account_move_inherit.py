#     'description': """
# 期间对账单、发票生成、会计扩展字段
#     """,

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
    waybill_bill_number = fields.Char(string="Waybill Bill Number", copy=False)

    def action_push_customer_invoice_files_to_period(self):
        for rec in self:
            if rec.move_type != "out_invoice":
                raise ValidationError(_("Only customer invoices can push files to statement period."))

            statement_period_id = self.env["statement.period"].search([
                ("customer_invoice_id", "=", rec.id),

            ], limit=1)
            if not statement_period_id:
                raise ValidationError(_("No statement period found for this invoice."))
            attachments = self.env["ir.attachment"].sudo().search([
                ("res_model", "=", "account.move"),
                ("res_id", "=", rec.id),
            ])
            if not attachments:
                raise ValidationError(_("No attachments found on this invoice."))

            period = statement_period_id
            add_ids = [att_id for att_id in attachments.ids]
            period.write({"customer_invoice_attachment_ids": [(4, att_id) for att_id in add_ids]})

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Invoice files have been pushed to statement period."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_confirm_paid_sync_operation(self):
        for move in self:
            if move.move_type != "in_invoice":
                raise ValidationError(_("Only vendor bills can be confirmed."))
            if move.state != "posted":
                raise ValidationError(_("Vendor bill must be posted first."))
            if move.payment_state != "paid":
                raise ValidationError(_("Vendor bill is not fully paid."))
            if not move.bank_proof_attachment_ids:
                raise ValidationError(_("Bank proof (water slip) is required."))

            handover_line_env = self.env["operation.order.handover.invoice.line"]
            clearance_line_env = self.env["operation.order.clearance.invoice.line"]

            handover_lines = handover_line_env.sudo().search([("vendor_invoice_id", "=", move.id)])
            clearance_lines = clearance_line_env.sudo().search([("vendor_invoice_id", "=", move.id)])

            if not handover_lines and not clearance_lines:
                raise ValidationError(_("No related handover/clearance invoice line found."))

            now = fields.Datetime.now()

            for line in handover_lines:
                if line.payment_state != "paid":
                    line.write({"payment_state": "paid", "paid_user_id": self.env.user.id, "paid_time": now})
                new_attach_ids = []
                for att in move.bank_proof_attachment_ids:
                    new_att = att.copy({"res_model": "operation.order.handover.invoice.line", "res_id": line.id})
                    new_attach_ids.append(new_att.id)
                if new_attach_ids:
                    line.write({"bank_proof_attachment_ids": [(4, att_id) for att_id in new_attach_ids]})

            for line in clearance_lines:
                if line.payment_state != "paid":
                    line.write({"payment_state": "paid", "paid_user_id": self.env.user.id, "paid_time": now})
                new_attach_ids = []
                for att in move.bank_proof_attachment_ids:
                    new_att = att.copy({"res_model": "operation.order.clearance.invoice.line", "res_id": line.id})
                    new_attach_ids.append(new_att.id)
                if new_attach_ids:
                    line.write({"bank_proof_attachment_ids": [(4, att_id) for att_id in new_attach_ids]})

            handover_lines.mapped("handover_id").action_recompute_state()
            clearance_lines.mapped("clearance_id").action_recompute_state()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Payment Paid"), "message": _("Payment sync completed."), "type": "success",
                       "sticky": False},
        }

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
