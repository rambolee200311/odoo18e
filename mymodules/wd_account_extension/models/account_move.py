# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import AccessError, ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    bank_proof_attachment_ids = fields.Many2many("ir.attachment", "account_move_bank_proof_attachment_rel", "move_id", "attachment_id", string="Bank Proof Attachments", copy=False, tracking=True)
    payment_info_synced = fields.Boolean(string="Payment Information Synced", readonly=True, copy=False, tracking=True)
    invoice_request_user_id = fields.Many2one("res.users", string="Invoice Applicant", readonly=True, index=True, copy=False, tracking=True)
    waybill_bill_number = fields.Char(string="Bill of Lading", readonly=True, index=True, copy=False)
    project_id = fields.Many2one("project.project", string="Project", readonly=True, ondelete="restrict", index=True, copy=False)
    invoice_no = fields.Char(string="Invoice No", readonly=True, index=True, copy=False)
    eta = fields.Date(string="ETA", readonly=True, index=True, copy=False)

    def check_invoice_applicant_permission(self):
        if not self.env.user.has_group("wd_account_extension.group_invoice_applicant"):
            raise AccessError(_("Only invoice applicants can submit invoice requests."))

    def action_force_register_payment(self):
        vendor_bills = self.filtered(lambda move: move.move_type == "in_invoice")
        if len(vendor_bills.mapped("partner_id")) > 1:
            raise ValidationError(_("Only vendor bills from the same vendor can be paid together."))
        return super().action_force_register_payment()

    def action_post_invoice_request(self):
        self.check_invoice_applicant_permission()
        for rec in self:
            if rec.move_type != "in_invoice" or rec.invoice_request_user_id != self.env.user:
                raise AccessError(_("You can only post your own vendor bill request."))
        return self.sudo().action_post()

    def action_cancel_invoice_request(self):
        self.check_invoice_applicant_permission()
        for rec in self:
            if rec.move_type != "in_invoice" or rec.invoice_request_user_id != self.env.user:
                raise AccessError(_("You can only revoke your own vendor bill request."))
            move = rec.sudo()
            if move.state == "posted":
                move.button_draft()
            if move.state == "draft":
                move.button_cancel()
        return True


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    charge_item_id = fields.Many2one("world.depot.charge.item", string="Charge Item", ondelete="restrict", copy=False, index=True)
    waybill_bill_number = fields.Char(related="move_id.waybill_bill_number", string="Bill of Lading", store=True, readonly=True, index=True)
    project_id = fields.Many2one(related="move_id.project_id", string="Project", store=True, readonly=True, index=True)
    invoice_no = fields.Char(related="move_id.invoice_no", string="Invoice No", store=True, readonly=True, index=True)
    eta = fields.Date(related="move_id.eta", string="ETA", store=True, readonly=True, index=True)
