# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import ValidationError


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    bank_proof_attachment_ids = fields.Many2many("ir.attachment", "account_payment_register_bank_proof_attachment_rel", "payment_register_id", "attachment_id", string="Bank Proof (Water Slip)", copy=False)

    def action_create_payments(self):
        for rec in self:
            vendor_bills = rec.line_ids.move_id.filtered(lambda move: move.move_type == "in_invoice")
            if len(vendor_bills.mapped("partner_id")) > 1:
                raise ValidationError(_("Only vendor bills from the same vendor can be paid together."))
            if vendor_bills and not rec.bank_proof_attachment_ids:
                raise ValidationError(_("Bank proof (water slip) is required before creating payment."))
            vendor_bills.write({"bank_proof_attachment_ids": [(4, attachment.id) for attachment in rec.bank_proof_attachment_ids]})
        return super().action_create_payments()
