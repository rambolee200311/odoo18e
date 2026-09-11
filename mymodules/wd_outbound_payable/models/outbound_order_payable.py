# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class OutboundOrder(models.Model):
    _inherit = "world.depot.outbound.order"

    payable_lines = fields.One2many("world.depot.outbound.order.payable", "outbound_order_id", string="Payables",
                                    copy=False)


class OutboundOrderPayable(models.Model):
    _name = "world.depot.outbound.order.payable"
    _description = "Outbound Order Payable"
    _order = "id desc"

    outbound_order_id = fields.Many2one("world.depot.outbound.order", string="Outbound Order", required=True,
                                        ondelete="cascade", index=True, copy=False)
    company_id = fields.Many2one("res.company", string="Company", required=True, default=lambda self: self.env.company,
                                 index=True, copy=False)
    vendor_partner_id = fields.Many2one("res.partner", string="Vendor", required=True, ondelete="restrict", index=True)
    vendor_invoice_num = fields.Char(string="Vendor Invoice No", index=True, copy=False)
    payable_date = fields.Date(string="Payable Date", required=True, default=fields.Date.context_today, index=True)
    currency_id = fields.Many2one("res.currency", string="Currency", required=True, index=True,
                                  default=lambda self: self.default_currency_id())

    amount_total = fields.Monetary(string="Total Amount", currency_field="currency_id", compute="_compute_amount_total",
                                   store=True)
    charge_lines = fields.One2many("world.depot.outbound.order.payable.charge", "payable_id", string="Charge Lines",
                                   copy=False)
    vendor_invoice_attachment_ids = fields.Many2many("ir.attachment",
                                                     "wd_outbound_payable_vendor_invoice_attachment_rel", "payable_id",
                                                     "attachment_id", string="Vendor Invoice Attachments", copy=False)
    vendor_invoice_id = fields.Many2one("account.move", string="Vendor Bill", ondelete="restrict", index=True,
                                        copy=False)
    payment_state = fields.Selection([("draft", "Draft"), ("paying", "Payment Requested"), ("paid", "Paid")],
                                     string="Payment Status", required=True, default="draft", index=True, copy=False)
    apply_user_id = fields.Many2one("res.users", string="Applicant", readonly=True, index=True, copy=False)
    apply_datetime = fields.Datetime(string="Application Time", readonly=True, copy=False)
    bank_proof_attachment_ids = fields.Many2many("ir.attachment", "wd_outbound_payable_bank_proof_attachment_rel",
                                                 "payable_id", "attachment_id", string="Bank Proof Attachments",
                                                 readonly=True, copy=False)
    paid_user_id = fields.Many2one("res.users", string="Payment Confirmed By", readonly=True, index=True, copy=False)
    paid_datetime = fields.Datetime(string="Payment Confirmation Time", readonly=True, copy=False)
    remark = fields.Text(string="Remark")

    @api.model
    def default_currency_id(self):
        # outbound_order_id = self.env.context.get("default_outbound_order_id")
        # if outbound_order_id:
        #     outbound_order = self.env["world.depot.outbound.order"].sudo().browse(outbound_order_id)
        #     if outbound_order.currency_id:
        #         return outbound_order.currency_id.id
        return self.env.company.currency_id.id

    @api.constrains("outbound_order_id", "vendor_invoice_num")
    def check_vendor_invoice_num(self):
        payable_model = self.env["world.depot.outbound.order.payable"]
        for rec in self:
            invoice_num = (rec.vendor_invoice_num or "").strip()
            if not invoice_num or not rec.outbound_order_id:
                continue
            duplicate_count = payable_model.sudo().search_count([
                ("outbound_order_id", "=", rec.outbound_order_id.id),
                ("vendor_invoice_num", "=", invoice_num),
                ("id", "!=", rec.id),
            ])
            if duplicate_count:
                raise ValidationError(_("Vendor invoice number must be unique within the same outbound order."))

    @api.constrains("vendor_invoice_attachment_ids", "amount_total")
    def check_vendor_invoice_attachment(self):
        for rec in self:
            if rec.vendor_invoice_attachment_ids and rec.amount_total <= 0:
                raise ValidationError(
                    _("The total amount must be greater than zero when vendor invoice attachments are provided."))

    @api.depends("charge_lines.amount", "charge_lines.manual_amount_total")
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(
                line.manual_amount_total if line.manual_amount_total > 0 else line.amount for line in rec.charge_lines)

    def action_request_payment(self):
        for rec in self:
            if rec.payment_state != "draft":
                raise ValidationError(_("Only draft outbound payables can request payment."))
            if rec.vendor_invoice_id:
                raise ValidationError(_("This outbound payable is already linked to a vendor bill."))
            if not rec.vendor_invoice_num:
                raise ValidationError(_("Vendor Invoice No is required before requesting payment."))
            if not rec.charge_lines:
                raise ValidationError(_("At least one charge line is required before requesting payment."))
            if not rec.vendor_invoice_attachment_ids:
                raise ValidationError(_("Vendor invoice attachments are required before requesting payment."))
            invalid_charge_lines = rec.charge_lines.filtered(
                lambda line: (line.manual_amount_total if line.manual_amount_total > 0 else line.amount) <= 0)
            if invalid_charge_lines:
                raise ValidationError(_("Each charge line amount must be greater than zero."))
            journal = self.env["account.journal"].sudo().search(
                [("type", "=", "purchase"), ("company_id", "=", rec.company_id.id)], limit=1)
            if not journal:
                raise ValidationError(_("No purchase journal is configured for the current company."))
            env_account = self.env["account.account"]
            expense_account = env_account.sudo().search([
                ("code", "=", "WDP400001"),
                ("account_type", "=", "expense"),
                ("company_ids", "in", rec.env.company.id),
            ], limit=1)
            if not expense_account:
                raise ValidationError(_("Clearance expense account WDA5002 is not configured."))
            invoice_line_vals = []
            for line in rec.charge_lines:
                quantity = 1.0 if line.manual_amount_total > 0 else line.quantity
                unit_price = line.manual_amount_total if line.manual_amount_total > 0 else line.unit_price
                invoice_line_vals.append(
                    {"name": line.charge_item_id.display_name, "charge_item_id": line.charge_item_id.id, "quantity": quantity, "price_unit": unit_price,
                     "account_id": expense_account.id})
            vendor_bill = self.env["account.move"].create(
                {"move_type": "in_invoice", "partner_id": rec.vendor_partner_id.id, "invoice_date": rec.payable_date,
                 "currency_id": rec.currency_id.id, "journal_id": journal.id, "ref": rec.vendor_invoice_num,
                 "outbound_payable_id": rec.id,
                 "invoice_line_ids": [(0, 0, line_vals) for line_vals in invoice_line_vals]})
            for attachment in rec.vendor_invoice_attachment_ids:
                attachment.copy({"res_model": "account.move", "res_id": vendor_bill.id})
            vendor_bill.action_post()
            rec.write(
                {"vendor_invoice_id": vendor_bill.id, "payment_state": "paying", "apply_user_id": self.env.user.id,
                 "apply_datetime": fields.Datetime.now()})
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"type": "success", "message": _("Payment request submitted."),
                           "next": {"type": "ir.actions.client", "tag": "soft_reload"}}}

    def action_revoke_payment_request(self):
        for rec in self:
            if rec.payment_state != "paying" or not rec.vendor_invoice_id:
                raise ValidationError(_("Only payment requests with a vendor bill can be revoked."))
            vendor_bill = rec.vendor_invoice_id
            if vendor_bill.payment_state != "not_paid":
                raise ValidationError(_("A vendor bill with payment activity cannot be revoked."))
            if vendor_bill.state == "posted":
                vendor_bill.button_draft()
            if vendor_bill.state == "draft":
                vendor_bill.button_cancel()
            rec.write(
                {"vendor_invoice_id": False, "payment_state": "draft", "apply_user_id": False, "apply_datetime": False,
                 "bank_proof_attachment_ids": [(5, 0, 0)], "paid_user_id": False, "paid_datetime": False})
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"type": "success", "message": _("Payment request revoked."),
                           "next": {"type": "ir.actions.client", "tag": "soft_reload"}}}

    def unlink(self):
        for rec in self:
            if rec.payment_state != "draft" or rec.vendor_invoice_id:
                raise ValidationError(_("Only draft outbound payables without a vendor bill can be deleted."))
        return super().unlink()


class OutboundOrderPayableCharge(models.Model):
    _name = "world.depot.outbound.order.payable.charge"
    _description = "Outbound Order Payable Charge"

    payable_id = fields.Many2one("world.depot.outbound.order.payable", string="Payable", required=True,
                                 ondelete="cascade", index=True, copy=False)
    charge_item_id = fields.Many2one("world.depot.charge.item", string="Charge Item", required=True, index=True,
                                     ondelete="restrict")
    quantity = fields.Float(string="Quantity", required=True, default=1.0)
    charge_unit_id = fields.Many2one("world.depot.charge.unit", string="Unit")
    unit_price = fields.Monetary(string="Unit Price", required=True, default=0.0)
    manual_amount_total = fields.Monetary(string="Manual Total Amount", currency_field="currency_id", default=0.0)
    amount = fields.Monetary(string="Amount", currency_field="currency_id", compute="_compute_amount", store=True)
    currency_id = fields.Many2one("res.currency", string="Currency", related="payable_id.currency_id", store=True,
                                  readonly=True, index=True)
    remark = fields.Text(string="Remark")

    @api.depends("quantity", "unit_price")
    def _compute_amount(self):
        for rec in self:
            rec.amount = (rec.quantity or 0.0) * (rec.unit_price or 0.0)
