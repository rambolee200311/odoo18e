# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import datetime, time, timedelta
HANDOVER_STATE = [("open", "Open"),
         ("paying", "Paying"), ("paid", "Paid"), ("releasing", "Releasing"),
         ("released", "Released"), ("close", "Close"),
         ("cancelled", "Cancelled")]

class OperationOrderHandover(models.Model):
    _name = "operation.order.handover"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Handover Operation"
    _order = "id desc"

    name = fields.Char(string="Handover No.", required=True, copy=False, default=lambda self: _("New"), index=True)
    waybill_id = fields.Many2one("world.depot.waybill", string="Waybill", required=True, ondelete="restrict", index=True)
    bl_number = fields.Char(string='Bill of Lading',related='waybill_id.bl_number', index=True)  # NKGA84065  mbl
    hbl_number = fields.Char(string='House Bill of Lading',related='waybill_id.hbl_number', index=True)  # HBL123456789
    obl_number = fields.Char(string="OBL No",related='waybill_id.obl_number', index=True)
    bl_release_type = fields.Selection([
         ('original', 'Original BL'),
         ('telex', 'Telex Release'),
         ('seawaybill', 'Sea Waybill'),
         ('destination', 'Destination Release'),
         ('third_party', 'Third Party Release')], string="BL Release Type",
        default='original', required=True)

    waybill_bill_number = fields.Char(string="Waybill Bill Number", compute="_compute_waybill_bill_number", store=True)

    @api.depends("waybill_id.bl_number", "waybill_id.hbl_number", "waybill_id.obl_number")
    def _compute_waybill_bill_number(self):
        for rec in self:
            rec.waybill_bill_number = rec.waybill_id.bl_number or rec.waybill_id.hbl_number or rec.waybill_id.obl_number

    #外部系统
    external_system_type = fields.Selection([("tms", "TMS"), ("oms", "OMS"), ("other", "Other")], string="External System Type")
    external_system_no = fields.Char(string="External Order No.", index=True)
    sync_time = fields.Datetime(string="Sync Time")

    project_id = fields.Many2one("project.project", string="Project", related="waybill_id.project", store=True, readonly=True, index=True)
    # charge_quotation_id = fields.Many2one("charge.quotation", string="Charge Quotation", readonly=True)
    # currency_id = fields.Many2one("res.currency", string="Currency", related="waybill_id.currency_id", store=True)

    state = fields.Selection(
        HANDOVER_STATE,
        string="Status", default="open", required=True, tracking=True, index=True)
    #结算状态

    confirm_user_id = fields.Many2one("res.users", string="Confirmed By", readonly=True)
    confirm_time = fields.Datetime(string="Confirmed On", readonly=True)
    settle_user_id = fields.Many2one("res.users", string="Settled By", readonly=True)
    settle_time = fields.Datetime(string="Settled On", readonly=True)
    statement_period_id = fields.Many2one("statement.period", string="Statement Period",ondelete='set null')



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
    actual_pickup_datetime = fields.Datetime(string="Actual Pickup Date")
    remark = fields.Text(string="Remark")

    container_line_ids = fields.One2many("world.depot.waybill.container", "waybill_id", string="Containers", related="waybill_id.container_ids", readonly=True)

    container_qty = fields.Integer(string="Container Qty",related='waybill_id.container_qty', required= True)

    invoice_line_ids = fields.One2many("operation.order.handover.invoice.line", "handover_id", string="Vendor Invoice Lines", copy=False)

    attachment_line_ids = fields.One2many("operation.order.handover.attachment.line", "handover_id", string="Document Lines", copy=False)


    has_advance_invoice = fields.Boolean(string="Has Advance Invoice", compute="_compute_payment_summary", store=True)
    has_unpaid_advance_invoice = fields.Boolean(string="Has Unpaid Advance Invoice", compute="_compute_payment_summary", store=True)
    all_advance_paid = fields.Boolean(string="All Advance Paid", compute="_compute_payment_summary", store=True)

    # 费用明细
    charge_line_ids = fields.One2many("operation.order.handover.charge.line", "handover_id", string="Charges", copy=False)
    cost_line_ids = fields.One2many("operation.order.handover.cost.line", "handover_id", string="Costs", copy=False)
    currency_id = fields.Many2one("res.currency", string="Currency", related="waybill_id.quotation_id.currency_id", store=True)

    container_nums = fields.Char(string="Container Nums", compute="_compute_container_nums")
    amount_total_change = fields.Monetary(string="Total Amount", currency_field="currency_id", compute="_compute_amount_total_change")

    manual_amount_total_change = fields.Monetary(string="Manual Total Amount", currency_field="currency_id", default=0.0,
                                          tracking=True)
    statement_period_id_state = fields.Selection([], string="Statement Period State",
                                                 related="statement_period_id.state", store=True)
    parent_id = fields.Many2one("operation.order.handover", string=" Partner Operation", index=True)
    child_ids = fields.One2many('operation.order.handover', 'parent_id', string="Child Handover")
    extra_reason = fields.Selection([('customs_inspection', 'Customs Inspection'),
                                     ('detention', 'Detention'),
                                     ('split_container', 'Split Container'),
                                     ('clearance_exception', 'Clearance Exception'),
                                     ('service_add', 'Additional Service'),
                                     ('other', 'Other')],
                                    string="Additional Reason")

    actual_datetime = fields.Datetime(string="Actual Date")
    extra_remark = fields.Char(string="Additional Remark")

    #逾期字段
    is_handover_overdue = fields.Boolean(string="Is Handover Overdue", compute="_compute_is_handover_overdue",default=False)
    overdue_blocking_reason_id = fields.Many2one("operation.blocking.reason", string="Overdue Blocking Reason",
                                                 index=True, copy=False, tracking=True)
    overdue_blocking_reason_short_name = fields.Char(related='overdue_blocking_reason_id.short_name',store=True)
    overdue_reason_note = fields.Text(string="Overdue Reason Note", tracking=True, copy=False)

    overdue_handle_result = fields.Selection([
        ("backfill_done", "Backfilled Handover Done"),
        ("urge_customer", "Urged Customer Payment/Documents"),
        ("contact_ship_agent", "Contacted Shipping Line/Agent"),
        ("resubmit_docs", "Resubmitted Correct Documents"),
        ("other", "Other"),
    ], string="Overdue Handle Result", index=True, copy=False, tracking=True)
    overdue_result_note = fields.Text(string="Overdue Result Note", tracking=True, copy=False)

    @api.onchange("do_issue_datetime", "attachment_line_ids")
    def onchange_do_release_document_required(self):
        self.check_do_release_document_required()

    @api.constrains("do_issue_datetime", "attachment_line_ids")
    def check_do_release_document_required(self):
        for rec in self:
            if not rec.do_issue_datetime:
                continue

            do_files = rec.attachment_line_ids.filtered(
                lambda line: line.doc_type == "do" and line.file
            )
            if not do_files:
                raise ValidationError(
                    _("DO / Telex Release document is required when DO Issue Date is filled.")
                )

    @api.constrains("overdue_blocking_reason_id", "overdue_reason_note", "overdue_handle_result", "overdue_result_note")
    def check_handover_overdue_other_notes(self):
        for rec in self:
            reason_code = rec.overdue_blocking_reason_id.short_name if rec.overdue_blocking_reason_id else False
            if reason_code == "Others + Exp" and not (rec.overdue_reason_note or "").strip():
                raise ValidationError(_("Reason Note is required when Blocking Reason is Others."))
            if rec.overdue_handle_result == "other" and not (rec.overdue_result_note or "").strip():
                raise ValidationError(_("Result Note is required when Handle Result is Other."))


    @api.depends("state", "waybill_id.ata", "waybill_id.eta")
    def _compute_is_handover_overdue(self):
        rule = self.env["operation.workbench.alert.rule"].get_rule_values(company_id=self.env.company.id)
        available_days = int(rule.get("handover_available_days", 3))

        now_dt = fields.Datetime.now()
        for rec in self:
            rec.is_handover_overdue = False

            if rec.state == "cancelled":
                continue
            base_date = rec.waybill_id.ata or rec.waybill_id.eta
            if not base_date:
                continue
            base_date_value = fields.Date.to_date(base_date)
            base_dt = datetime.combine(base_date_value, time(23, 59, 59))
            handover_due_datetime = base_dt + timedelta(days=available_days)

            compare_datetime = rec.do_issue_datetime or now_dt
            rec.is_handover_overdue = compare_datetime >= handover_due_datetime

    def action_create_child_handover(self):
        self.ensure_one()
        if self.state != 'close':
            raise ValidationError(_("Handover must be close before creating child clearance."))
        vals = self.copy_data()[0]

        child_count = self.env['operation.order.handover'].search_count([
            ('parent_id', '=', self.id)
        ]) + 1

        vals.update({
            "parent_id": self.id,
            "name": f"{self.name}-{child_count}",
            "attachment_line_ids": [(0, 0, {
                "doc_type": line.doc_type,
                "remark": line.remark,
                "file": line.file,
                "name": line.name,
            }) for line in self.attachment_line_ids],
        })

        vals.pop("charge_line_ids", None)
        vals.pop("invoice_line_ids", None)

        child = self.sudo().create(vals)

        return {
            "type": "ir.actions.act_window",
            "name": "Child Handover",
            "res_model": "operation.order.handover",
            "view_mode": "form",
            "views": [(self.env.ref("wd_iffm.view_operation_order_handover_child_form").id, "form")],
            "res_id": child.id,
        }

    def action_create_child_handover_workbench(self):
        env_handover = self.env["operation.order.handover"]
        for rec in self:
            if rec.parent_id:
                raise ValidationError(_("Only the main switch bill can create a sub-switch bill."))

            child_count = env_handover.sudo().search_count([("parent_id", "=", rec.id)]) + 1

            vals = {
                "waybill_id": rec.waybill_id.id,
                "parent_id": rec.id,
                "name": f"{rec.name}-{child_count}",
                "external_system_type": rec.external_system_type,
                "external_system_no": rec.external_system_no,
                "voyage_no": rec.voyage_no,
                "do_no": rec.do_no,
                "do_issue_datetime": rec.do_issue_datetime,
                "expected_pickup_datetime": rec.expected_pickup_datetime,
                "actual_pickup_datetime": rec.actual_pickup_datetime,
                "actual_datetime": rec.actual_datetime,
                "extra_reason": rec.extra_reason,
                "extra_remark": rec.extra_remark,
                "remark": rec.remark,
                "state": "open",
                "attachment_line_ids": [
                    (0, 0, {"doc_type": line.doc_type, "remark": line.remark, "file": line.file, "name": line.name}) for
                    line in rec.attachment_line_ids],
                # "charge_line_ids": [(0, 0, {"charge_item_id": line.charge_item_id.id,
                #                             "charge_origin_type": line.charge_origin_type, "qty": line.qty,
                #                             "unit_price": line.unit_price,
                #                             "manual_amount_total": line.manual_amount_total, "remark": line.remark}) for
                #                     line in rec.charge_line_ids],
            }
            child = env_handover.create(vals)

            return {
                "ok": True,
                "message": _("Child handover created successfully."),
                "child": {
                    "id": child.id,
                    "name": child.name,
                    "state": child.state,
                    "parent_id": child.parent_id.id,
                    "container_qty": child.container_qty,
                },
            }



    @api.constrains('extra_reason', 'extra_remark')
    def check_extra_remark(self):
        for rec in self:
            if rec.extra_reason == 'other' and not rec.extra_remark:
                raise ValidationError(_("Remark is required when reason is Other."))


    def action_handover_remove_from_statement_period(self):
        for record in self:
            if not record.statement_period_id:
                continue
        self.write({'statement_period_id': False})
        return True


    @api.depends('charge_line_ids')
    def _compute_amount_total_change(self):
        for record in self:
            total_amount = 0.0
            for charge_line in record.charge_line_ids:
                amount = charge_line.manual_amount_total if charge_line.manual_amount_total > 0 else charge_line.amount_total
                total_amount += amount
            record.amount_total_change = total_amount

    @api.depends('container_line_ids')
    def _compute_container_nums(self):
        for record in self:
            container_numbers = [line.container_number for line in record.container_line_ids]
            record.container_nums = ', '.join(container_numbers)

    # @api.onchange("waybill_id")
    # def _onchange_waybill_id(self):
    #     for rec in self:
    #         if rec.waybill_id:
    #             rec.attachment_line_ids = [(5, 0, 0)]
    #             rec.charge_line_ids = [(5, 0, 0)]
    #             attachment_lines = [(0, 0, {
    #                 "doc_type": ln.bill_doc_type,
    #                 "remark": ln.description,
    #                 "file": ln.file,
    #                 "name": ln.filename,
    #             }) for ln in rec.waybill_id.other_docs_ids]
    #
    #             charge_lines = [(0, 0, {
    #                 "charge_item_id": ln.charge_item_id.id,
    #                 "charge_origin_type": 'quotation',
    #                 "unit_price": ln.unit_price,
    #             }) for ln in rec.waybill_id.project.quotation_id.quotation_thc_lines]
    #
    #             rec.project_id = rec.waybill_id.project
    #             rec.container_qty = rec.waybill_id.container_qty
    #             rec.attachment_line_ids =  attachment_lines
    #             rec.charge_line_ids = charge_lines
    #         else:
    #             rec.project_id = False
    #             rec.container_qty = False
    #             rec.attachment_line_ids = [(5, 0, 0)]
    #             rec.charge_line_ids = [(5, 0, 0)]

    @api.constrains("waybill_id", "state")
    def _constrain_unique_waybill(self):
        env_model = self.env["operation.order.handover"]
        for rec in self:
            if rec.parent_id:
                continue
            if not rec.waybill_id:
                continue
            domain = [
                ("waybill_id", "=", rec.waybill_id.id),
                ("parent_id", "=", False),
                ("state", "!=", "cancelled"),
            ]
            if rec.id:
                domain.append(("id", "!=", rec.id))

            count = env_model.sudo().search_count(domain)
            if count:
                raise ValidationError(
                    _("This waybill is already used by another active handover order.")
                )

    @api.depends("invoice_line_ids.handover_cost_line_ids.cost_nature", "invoice_line_ids.payment_state")
    def _compute_payment_summary(self):
        for rec in self:
            lines = rec.invoice_line_ids
            states = set(lines.mapped("payment_state"))

            rec.has_advance_invoice = bool(lines)
            rec.has_unpaid_advance_invoice = bool(lines.filtered(lambda l: l.payment_state != "paid"))
            rec.all_advance_paid = bool(lines) and states == {"paid"}



    def action_recompute_state(self):
        for rec in self:
            if rec.state in ("releasing", "released", "close", "cancelled"):
                continue
            lines = rec.invoice_line_ids
            if not lines:
                rec.write({"state": "open"})
                continue

            states = set(lines.mapped("payment_state"))
            if states == {"draft"}:
                rec.write({"state": "open"})
            elif states == {"paid"}:
                rec.write({"state": "paid"})
            else:
                rec.write({"state": "paying"})

    def action_releasing(self):
        for rec in self:
            rec.check_releasing_ready()
            rec.write({"state": "releasing"})

    def action_released(self):
        for rec in self:
            rec.check_released_ready()
            rec.write({"state": "released",
                       })
            rec.waybill_id.write({
                "release_received": True
            })

    def action_close(self):
        for rec in self:
            if rec.parent_id:
                if not rec.charge_line_ids:
                    raise ValidationError(_("Charges are required before Close."))
                unpaid = rec.invoice_line_ids.filtered(
                    lambda l: l.payment_state != "paid")
                if unpaid:
                    raise ValidationError(_("All advance invoices must be paid before Close."))
            else:
                rec.check_close_ready()
            rec.write({
                "state": "close"
            })


    # 暂不用
    def action_cancelled(self):
        for rec in self:
            rec.write({"state": "cancelled"})



    def get_required_doc_count(self, doc_type):
        self.ensure_one()
        lines = self.attachment_line_ids.filtered(lambda l: l.doc_type == doc_type and l.file)
        return len(lines)


    def check_releasing_ready(self):
        for rec in self:
            if rec.state not in ("paying", "paid"):
                raise ValidationError(_("Only Apply/Paying/Paid can go to Releasing."))
            if rec.has_advance_invoice and not rec.all_advance_paid:
                raise ValidationError(_("All advance invoices must be paid before Releasing."))

    def check_released_ready(self):
        for rec in self:
            if rec.state != "releasing":
                raise ValidationError(_("Only Releasing can be set to Released."))
            if rec.get_required_doc_count("do") == 0:
                raise ValidationError(_("DO / Telex Release document is required before Released."))
            if not rec.waybill_id.ata or not rec.waybill_id.terminal_id:
                raise ValidationError(_("Waybill ETA and Terminal of Arrival is required before Released."))
            if not rec.do_issue_datetime:
                raise ValidationError(_("Do issue date is required."))
            if not rec.bl_release_type:
                raise ValidationError(_("BL Release type is required."))

    def check_close_ready(self):
        for rec in self:
            if rec.state != "released":
                raise ValidationError(_("Only Released can be closed."))
            if rec.get_required_doc_count("do") == 0:
                raise ValidationError(_("DO / Telex Release document is required before Close."))
            if len(rec.charge_line_ids) == 0:
                raise ValidationError(_("Charges are required before Close."))

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

    handover_id = fields.Many2one("operation.order.handover", string="Handover", index=True)
    shipping_line_id = fields.Many2one("res.partner", string="Vendor (Shipping Line / Agent)", related='handover_id.shipping_line_id', store=True,index=True)
    vendor_invoice_id = fields.Many2one("account.move", string="Vendor Invoice (Optional)", ondelete="set null", index=True)
    invoice_date = fields.Date(string="Invoice Date",required=True, default=fields.Date.context_today)
    currency_id = fields.Many2one("res.currency", string="Currency", required=True, index=True,
                                  default=lambda self: self.default_currency_id())

    @api.model
    def default_currency_id(self):
        handover_id = self.env.context.get("default_handover_id")
        if handover_id:
            handover = self.env["operation.order.handover"].sudo().browse(handover_id)
            return handover.currency_id.id
        return self.env.company.currency_id.id

    amount_total = fields.Monetary(string="Amount", currency_field="currency_id", compute="_compute_amount_total", store=True)

    payment_state = fields.Selection([("draft", "Draft"), ("paying", "Paying"), ("paid", "Paid"), ("customer_paid", "Customer Paid")], string="Payment State", default="draft", required=True, index=True)
    vendor_invoice_num = fields.Char(string="Vendor Invoice No")
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
    handover_cost_line_ids = fields.One2many("operation.order.handover.cost.line", "handover_invoice_line_id", string="Cost Lines")
    remark = fields.Text(string="Remark")
    apply_user_id = fields.Many2one("res.users", string="Apply User", readonly=True, copy=False, index=True)
    apply_datetime = fields.Datetime(string="Apply Datetime", readonly=True, copy=False)
    #会计对账

    payment_journal_id = fields.Many2one("account.journal", string="Payment Journal",
                                         domain=[("type", "in", ("bank", "cash"))])
    payment_id = fields.Many2one("account.payment", string="Payment", readonly=True)

    payment_company_id = fields.Many2one("res.partner", string="Payment Company",
                                         default=lambda self: self.default_payment_company_id(), index=True)
    receipt_company_id = fields.Many2one("res.partner", string="Receipt Company", index=True)

    @api.model
    def default_payment_company_id(self):
        handover_id = self.env.context.get("default_handover_id")
        if handover_id:
            handover = self.env["operation.order.handover"].sudo().browse(handover_id)
            return handover.project_id.payment_company_id.id if handover.project_id.payment_company_id else False
        return False

    @api.onchange("handover_id")
    def onchange_handover_id(self):
        for rec in self:
            if rec.handover_id and not rec.payment_company_id:
                rec.payment_company_id = rec.handover_id.project_id.payment_company_id
    @api.constrains("vendor_invoice_num")
    def check_vendor_invoice_num(self):
        for rec in self:
            if rec.vendor_invoice_num and self.search_count([("vendor_invoice_num", "=", rec.vendor_invoice_num), ("id", "!=", rec.id)]):
                raise ValidationError(_("Vendor Invoice No must be unique."))

    @api.constrains("vendor_invoice_attachment_ids", "amount_total")
    def check_vendor_invoice_attachment(self):
        for rec in self:
            if rec.vendor_invoice_attachment_ids and rec.amount_total <= 0:
                raise ValidationError(_("Invoice Amount must be greater than 0."))

    @api.depends("handover_cost_line_ids.amount_total", "handover_cost_line_ids.manual_amount_total")
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(
                (line.manual_amount_total if (line.manual_amount_total or 0.0) > 0 else (line.amount_total or 0.0))
                for line in rec.handover_cost_line_ids
            )


    def action_request_payment(self):
        move_model = self.env["account.move"]
        for rec in self:
            if rec.handover_id.is_handover_overdue:
                if not rec.handover_id.overdue_blocking_reason_id:
                    raise ValidationError(_("Overdue blocking reason is required for overdue handovers."))
                if not rec.handover_id.overdue_handle_result:
                    raise ValidationError(_("Overdue handle result is required for overdue handovers."))

            operator = self.env.ref("base.user_admin")
            if not rec.handover_cost_line_ids:
               raise ValidationError(_("Cost lines are required before requesting payment."))

            if rec.amount_total <= 0 and not rec.vendor_invoice_attachment_ids:
                raise ValidationError(_("Amount or vendor invoice is required before requesting payment."))

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

            if not rec.handover_cost_line_ids:
                expense_account = (self.env["account.account"].sudo().search
                                   ([("account_type", "=", "expense"), ("company_ids", 'in', rec.env.company.id),
                                     ('code', '=', 'WDP400001')], limit=1))
                if not expense_account:
                    raise ValidationError(
                        _("Fallback account not found. Please configure it (code=WDP400001)."))
                line_name = _("Handover Bill - %s") % (rec.handover_id.name,)
                invoice_lines = [(0, 0, {
                    "name": line_name,
                    "quantity": 1.0,
                    "price_unit": rec.amount_total or 0.0,
                    "account_id": expense_account.id,
                })]

            else:
                invoice_lines = []
                for cost in rec.handover_cost_line_ids:
                    account = cost.charge_item_id.account_account_id
                    if not account:
                        raise ValidationError(_("Account not found for charge item %s.") % (cost.charge_item_id.item_name,))
                    price = cost.manual_amount_total if cost.manual_amount_total>0 else cost.amount_total
                    name= _("Handover Bill - %s") % (cost.charge_item_id.item_name,)
                    invoice_lines.append((0, 0, {
                        "name": name,
                        "quantity": cost.qty or 1.0,
                        "price_unit": price or 0.0,
                        "account_id": account.id,
                    }))
            waybill = rec.handover_id.waybill_id
            waybill_bill_number = waybill.bl_number or waybill.hbl_number or waybill.obl_number or False

            move_vals = {
                "move_type": "in_invoice",
                "partner_id": rec.receipt_company_id.id,
                "invoice_date": rec.invoice_date or fields.Date.context_today(rec),
                "currency_id": rec.currency_id.id,
                "journal_id": journal.id,
                "ref": f"{rec.handover_id.name}/{rec.id}",
                "waybill_bill_number": waybill_bill_number,
                "invoice_line_ids": invoice_lines,
            }
            move = move_model.with_user(operator).create(move_vals)

            rec.write({
                "apply_user_id": self.env.user.id,
                "apply_datetime": fields.Datetime.now(),
            })

            if rec.vendor_invoice_attachment_ids:
                rec.vendor_invoice_attachment_ids.with_user(operator).copy({
                    "res_model": "account.move",
                    "res_id": move.id,
                })

            # 过账（posted）
            move.with_user(operator).action_post()
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
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }

    def action_revoke_payment_request(self):
        for rec in self:
            operator = self.env.ref("base.user_admin")
            if rec.payment_state != "paying":
                raise ValidationError(_("Only paying invoice line can be revoked."))
            if not rec.vendor_invoice_id:
                raise ValidationError(_("No linked vendor invoice found."))

            move = rec.vendor_invoice_id
            if move.payment_state != "not_paid":
                raise ValidationError(_("Linked vendor invoice already has payment, revoke is not allowed."))

            if move.state == "posted":
                move.button_draft()
            if move.state == "draft":
                move.with_user( operator).button_cancel()

            rec.write({
                "payment_state": "draft",
                "vendor_invoice_id": False,
                "payment_id": False,
                "paid_user_id": False,
                "paid_time": False,
                "apply_user_id": False,
                "apply_datetime": False,
                "bank_proof_attachment_ids": [(5, 0, 0)],
            })

        self.mapped("handover_id").action_recompute_state()
        view_xmlid = "wd_iffm.operation_order_handover_invoice_line_form_view"
        return {
            "type": "ir.actions.act_window",
            "name": _("Invoice Line"),
            "res_model": self._name,
            "view_mode": "form",
            "views": [(self.env.ref(view_xmlid).id, "form")],
            "res_id": self.id,
            "target": "new",
        }
    def unlink(self):
        for rec in self:
            if rec.payment_state in ("paying", "paid", "customer_paid"):
                raise ValidationError(_("Cannot delete invoice line that is already paid."))

            if rec.vendor_invoice_id:
                if rec.vendor_invoice_id.state == "posted":
                    raise ValidationError(_("Cannot delete invoice line linked to a posted vendor bill."))
                raise ValidationError(
                    _("This invoice line is linked to a vendor bill. "
                      "Please delete or cancel the vendor bill first.")
                )

        return super().unlink()

