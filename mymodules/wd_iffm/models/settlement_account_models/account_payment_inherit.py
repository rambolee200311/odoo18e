from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class AccountPayment(models.Model):
    _inherit = "account.payment"


    # def action_validate(self):
    #     for rec in self:
    #         if rec.partner_type == "customer":
    #             if  not rec.attachment_ids:
    #                 raise ValidationError(_("Bank proof attachment is required before posting payment."))
    #     return super().action_validate()

class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    def action_create_payments(self):
        for rec in self:
            missing_proof_moves = rec.line_ids.move_id.filtered(
                lambda move: move.move_type == "in_invoice" and not move.bank_proof_attachment_ids
            )
            if missing_proof_moves:
                raise ValidationError(
                    _("Bank proof (water slip) is required before creating payment for: %s")
                    % ", ".join(missing_proof_moves.mapped("display_name"))
                )
        return super().action_create_payments()