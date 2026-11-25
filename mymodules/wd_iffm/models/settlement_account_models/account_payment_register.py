# -*- coding: utf-8 -*-

from odoo import models


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    def action_create_payments(self):
        result = super().action_create_payments()
        for rec in self:
            operation_vendor_bills = rec.line_ids.move_id.filtered(lambda move: move.move_type == "in_invoice" and (move.handover_id or move.clearance_id))
            operation_vendor_bills.action_confirm_paid_sync_operation()
        return result
