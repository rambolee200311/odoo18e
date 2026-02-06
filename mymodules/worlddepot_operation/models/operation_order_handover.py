# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OperationOrderHandover(models.Model):
    _name = "operation.order.handover"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Handover Operation"
    _order = "id desc"

    name = fields.Char(string="Handover No.", required=True, copy=False, default=lambda self: _("New"), index=True)
    waybill_id = fields.Many2one("world.depot.waybill", string="Waybill", required=True, ondelete="restrict", index=True)
    order_source = fields.Selection([("manual", "Manual"), ("external", "External"), ("import", "Import")],
                                    string="Order Source", default="manual", required=True, index=True)
    #外部系统
    external_system_type = fields.Selection([("tms", "TMS"), ("oms", "OMS"), ("other", "Other")], string="External System Type")
    external_system_no = fields.Char(string="External Order No.", index=True)
    sync_time = fields.Datetime(string="Sync Time")

    project_id = fields.Many2one("project.project", string="Project", related="waybill_id.project", store=True, readonly=True, index=True)
    charge_quotation_id = fields.Many2one("charge.quotation", string="Charge Quotation", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency")

    state = fields.Selection(
        [("open", "Open"), ("apply", "Apply"),
         ("paying", "Paying"), ("paid", "Paid"), ("releasing", "Releasing"),
         ("released", "Released"), ("close", "Close"),
         ("cancelled", "Cancelled")],
        string="Status", default="open", required=True, tracking=True, index=True)
    #结算状态
    settle_state = fields.Selection([("unbilled", "Unbilled"), ("billed", "Billed")],
                                    string="Settlement Status", default="unbilled", required=True, index=True)
    confirm_user_id = fields.Many2one("res.users", string="Confirmed By", readonly=True)
    confirm_time = fields.Datetime(string="Confirmed On", readonly=True)
    settle_user_id = fields.Many2one("res.users", string="Settled By", readonly=True)
    settle_time = fields.Datetime(string="Settled On", readonly=True)


    bl_type = fields.Selection([("original", "Original"), ("telex", "Telex Release"), ("sea_waybill", "Sea Waybill")], string="B/L Type", default="original", required=True, index=True)
    bl_issue_datetime = fields.Datetime(string="B/L Issue Date")
    shipping_line_id = fields.Many2one("res.partner",related="waybill_id.shipping", string="Shipping Line")
    voyage_no = fields.Char(string="Voyage No.", index=True)
    shipper = fields.Many2one("res.partner", related='waybill_id.shipper', string="Shipper/Exporter")#装
    consignee = fields.Many2one("res.partner",related='waybill_id.consignee', string="Consignee/Importer")#卸
    terminal_a = fields.Many2one("res.partner", related="waybill_id.terminal_a", string="Terminal of Arrival")#交
    eta = fields.Date(string="ETA", related="waybill_id.eta")
    ata = fields.Date(string='ATA', related="waybill_id.ata")

    #DO
    do_no = fields.Char(string="Delivery Order No.", index=True)
    do_issue_datetime = fields.Datetime(string="DO Issue Date")
    expected_pickup_datetime = fields.Datetime(string="Expected Pickup Date")
    actual_pickup_datetime = fields.Datetime(string="Actual Pickup Date", readonly=True)
    handover_datetime = fields.Datetime(string="Handover Completed On", readonly=True)
    remark = fields.Text(string="Remark")

    container_line_ids = fields.One2many("world.depot.waybill.container", "waybill_id", string="Containers", related="waybill_id.container_ids", readonly=True)

    container_qty = fields.Integer(string="Container Qty",required= True)

    invoice_line_ids = fields.One2many("operation.order.handover.invoice.line", "handover_id", string="Vendor Invoice Lines", copy=False)

    attachment_line_ids = fields.One2many("operation.order.attachment.line", "handover_id", string="Document Lines", copy=False)


    has_advance_invoice = fields.Boolean(string="Has Advance Invoice", compute="_compute_payment_summary", store=True)
    has_unpaid_advance_invoice = fields.Boolean(string="Has Unpaid Advance Invoice", compute="_compute_payment_summary", store=True)
    all_advance_paid = fields.Boolean(string="All Advance Paid", compute="_compute_payment_summary", store=True)

    # 费用明细
    charge_line_ids = fields.One2many("operation.order.charge.line", "handover_id", string="Charges", copy=False)
    agency_line_ids = fields.One2many("operation.order.agency.line", "handover_id", string="Agency", copy=False)
    cost_line_ids = fields.One2many("operation.order.cost.line", "handover_id", string="Costs", copy=False)
    amount_charge_total = fields.Monetary(string="AR Total", currency_field="currency_id", compute="_compute_totals",
                                         store=True)
    amount_agency_total = fields.Monetary(string="Agency Total", currency_field="currency_id",
                                          compute="_compute_totals", store=True)
    amount_cost_total = fields.Monetary(string="Cost Total", currency_field="currency_id", compute="_compute_totals",
                                        store=True)

    @api.depends("charge_line_ids.amount_total", "agency_line_ids.amount_total", "cost_line_ids.amount_total")
    def _compute_totals(self):
        for rec in self:
            rec.amount_charge_total = sum(rec.charge_line_ids.mapped("amount_total"))
            rec.amount_agency_total = sum(rec.agency_line_ids.mapped("amount_total"))
            rec.amount_cost_total = sum(rec.cost_line_ids.mapped("amount_total"))

    @api.constrains("waybill_id", "state")
    def _constrain_unique_waybill(self):
        for rec in self:
            if not rec.waybill_id:
                continue

            domain = [
                ("id", "!=", rec.id),
                ("waybill_id", "=", rec.waybill_id.id),
                ("state", "!=", "cancelled"),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    _("This waybill is already used by another active handover order.")
                )

    @api.depends("invoice_line_ids.payment_mode", "invoice_line_ids.payment_state")
    def _compute_payment_summary(self):
        for rec in self:
            advance_lines = rec.invoice_line_ids.filtered(lambda l: l.payment_mode == "advance")
            rec.has_advance_invoice = bool(advance_lines)
            rec.has_unpaid_advance_invoice = bool(advance_lines.filtered(lambda l: l.payment_state != "paid"))
            rec.all_advance_paid = bool(advance_lines) and not rec.has_unpaid_advance_invoice


    def action_apply(self):
        for rec in self:
            rec.check_apply_ready()
            rec.write({"state": "apply"})

    def action_recompute_state(self):
        for rec in self:
            if rec.state in ("releasing", "released", "close", "cancelled"):
                continue
            if rec.has_advance_invoice:
                rec.write({"state": "paid" if rec.all_advance_paid else "paying"})

    def action_releasing(self):
        for rec in self:
            rec.check_releasing_ready()
            rec.write({"state": "releasing"})

    def action_released(self):
        for rec in self:
            rec.check_released_ready()
            rec.write({"state": "released"})

    def action_close(self):
        for rec in self:
            rec.check_close_ready()
            rec.write({"state": "close"})
    # 暂不用
    def action_cancelled(self):
        for rec in self:
            rec.write({"state": "cancelled"})

    # ---------------- Document helpers ----------------
    @api.constrains("waybill_id", "attachment_line_ids")
    def constrain_required_documents(self):
        for rec in self:
            if rec.get_required_doc_count("poa") == 0:
                raise ValidationError(_("POA file is required."))
            if rec.get_required_doc_count("bl") == 0 and not getattr(rec.waybill_id, "bl_number", False):
                raise ValidationError(_("BL file is required."))

    def get_required_doc_count(self, doc_type):
        self.ensure_one()
        lines = self.attachment_line_ids.filtered(lambda l: l.doc_type == doc_type and l.attachment_ids)
        return len(lines)

    def check_apply_ready(self):
        for rec in self:
            if not rec.waybill_id:
                raise ValidationError(_("Waybill is required."))
            if rec.get_required_doc_count("poa") == 0:
                raise ValidationError(_("POA file is required before Apply."))
            if rec.get_required_doc_count("bl") == 0 and not getattr(rec.waybill_id, "bl_number", False):
                raise ValidationError(_("BL is required (BL file or BL number)."))
            if rec.get_required_doc_count("apply_mail") == 0:
                raise ValidationError(_("Apply email evidence is required before Apply."))

    def check_releasing_ready(self):
        for rec in self:
            if rec.state not in ("apply", "paying", "paid"):
                raise ValidationError(_("Only Apply/Paying/Paid can go to Releasing."))
            if rec.has_advance_invoice and not rec.all_advance_paid:
                raise ValidationError(_("All advance invoices must be paid before Releasing."))
            #在系统里上传申请邮件或系统里发邮件
            if rec.get_required_doc_count("release_mail") == 0:
                raise ValidationError(_("Release request evidence is required before Releasing.(Release File)"))

    def check_released_ready(self):
        for rec in self:
            if rec.state != "releasing":
                raise ValidationError(_("Only Releasing can be set to Released."))
            if rec.get_required_doc_count("do") == 0:
                raise ValidationError(_("DO / Telex Release document is required before Released."))

    def check_close_ready(self):
        for rec in self:
            if rec.state != "released":
                raise ValidationError(_("Only Released can be closed."))
            if rec.get_required_doc_count("do") == 0:
                raise ValidationError(_("DO / Telex Release document is required before Close."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("operation.order.handover") or _("New")
        return super().create(vals_list)


class OperationOrderHandoverInvoiceLine(models.Model):
    _name = "operation.order.handover.invoice.line"
    _description = "Handover Vendor Invoice Line"
    _order = "id desc"

    handover_id = fields.Many2one("operation.order.handover", string="Handover", required=True, ondelete="cascade", index=True)
    vendor_partner_id = fields.Many2one("res.partner", string="Vendor (Shipping Line / Agent)", related='handover_id.shipping_line_id', ondelete="restrict", index=True)
    vendor_invoice_id = fields.Many2one("account.move", string="Vendor Invoice (Optional)", ondelete="set null", index=True)
    invoice_date = fields.Date(string="Invoice Date",required= True)
    currency_id = fields.Many2one("res.currency", string="Currency", related="handover_id.currency_id", store=True, readonly=True)
    amount_total = fields.Monetary(string="Amount", currency_field="currency_id")

    payment_mode = fields.Selection([("advance", "Advance by Company"), ("customer_pay", "Paid by Customer")],
                                    string="Payment Mode", default="advance", required=True, index=True)
    payment_state = fields.Selection([("draft", "Draft"), ("paying", "Paying"), ("paid", "Paid"), ("customer_paid", "Customer Paid")], string="Payment State", default="draft", required=True, index=True)
    vendor_invoice_attachment_ids = fields.Many2many(
        "ir.attachment", "handover_invoice_vendor_attachment_rel",
        "invoice_line_id", "attachment_id",
        string="Vendor Invoice Attachments", copy=False
    )
    bank_proof_attachment_ids = fields.Many2many(
        "ir.attachment", "handover_invoice_bank_proof_attachment_rel",
        "invoice_line_id", "attachment_id", string="Bank Proof Attachments", copy=False)
    paid_user_id = fields.Many2one("res.users", string="Paid Confirmed By", readonly=True)
    paid_time = fields.Datetime(string="Paid Confirmed On", readonly=True)
    remark = fields.Text(string="Remark")

    #会计对账

    payment_journal_id = fields.Many2one("account.journal", string="Payment Journal",
                                         domain=[("type", "in", ("bank", "cash"))])
    payment_id = fields.Many2one("account.payment", string="Payment", readonly=True)
    def action_request_payment(self):
        move_model = self.env["account.move"]
        for rec in self:
            if rec.handover_id != "apply":
                raise ValidationError(_("Only apply invoice can request payment."))
            if rec.payment_mode != "advance":
                raise ValidationError(_("Only advance invoices can request payment."))
            if not rec.amount_total and not rec.vendor_invoice_attachment_ids:
                raise ValidationError(_("Amount or vendor invoice is required before requesting payment."))
            if not rec.handover_id.shipping_line_id:
                raise ValidationError(_("Shipping Line/Vendor is required."))

            if not rec.currency_id:
                raise ValidationError(_("Currency is required."))
                # 若已有关联账单，直接校验并推进状态
            if rec.vendor_invoice_id:
                if rec.vendor_invoice_id.move_type != "in_invoice":
                    raise ValidationError(_("Linked vendor invoice must be a Vendor Bill (in_invoice)."))
                if rec.vendor_invoice_id.state != "posted":
                    raise ValidationError(_("Vendor bill must be posted before requesting payment."))
                rec.write({"payment_state": "paying"})
                continue

            journal = self.env["account.journal"].sudo().search(
                [("type", "=", "purchase"), ("company_id", "=", rec.env.company.id),('code','=','BILL')], limit=1
            )
            if not journal:
                raise ValidationError(_("Purchase journal not found. Please configure a Purchase Journal."))

            expense_account = self.env["account.account"].sudo().search(
                [("account_type", "=", "expense"), ("company_ids", 'in', rec.env.company.id),('code','=','600100')], limit=1
            )
            if not expense_account:
                raise ValidationError(_("No expense account found. Please configure an expense account."))

            line_name = _("Handover Bill - %s") % (rec.handover_id.name,)
            move_vals = {
                "move_type": "in_invoice",
                "partner_id": rec.handover_id.shipping_line_id.id,
                "invoice_date": rec.invoice_date or fields.Date.context_today(rec),
                "currency_id": rec.currency_id.id,
                "journal_id": journal.id,
                "ref": rec.handover_id.name,
                "invoice_line_ids": [
                    (0, 0, {
                        "name": line_name,
                        "quantity": 1.0,
                        "price_unit": rec.amount_total or 0.0,
                        "account_id": expense_account.id,
                    })
                ],
            }
            move = move_model.create(move_vals)

            if rec.vendor_invoice_attachment_ids:
                rec.vendor_invoice_attachment_ids.copy({
                    "res_model": "account.move",
                    "res_id": move.id,
                })

            # 过账（posted）
            move.action_post()
            rec.write({
                "vendor_invoice_id": move.id,
                "payment_state": "paying",
            })
        self.mapped("handover_id").action_recompute_state()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Payment Requested"),
                "message": _("Payment request has been submitted successfully."),
                "type": "success",
                "sticky": False,
            },
        }

    def unlink(self):
        for rec in self:
            if rec.payment_state in ("paid", "customer_paid"):
                raise ValidationError(_("Cannot delete invoice line that is already paid."))

            if rec.vendor_invoice_id:
                if rec.vendor_invoice_id.state == "posted":
                    raise ValidationError(_("Cannot delete invoice line linked to a posted vendor bill."))
                raise ValidationError(
                    _("This invoice line is linked to a vendor bill. "
                      "Please delete or cancel the vendor bill first.")
                )

        return super().unlink()

