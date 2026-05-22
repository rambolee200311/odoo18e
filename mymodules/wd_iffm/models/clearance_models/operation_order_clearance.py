# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import datetime, time, timedelta
CLEARANCE_STATE = [("open", "Open"),
         ("paying", "Paying"), ("paid", "Paid"), ("clearancing", "Clearancing"),
         ("clearanced", "Clearanced"), ("close", "Close"),
         ("cancelled", "Cancelled")]

class OperationOrderClearance(models.Model):
    _name = "operation.order.clearance"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Clearance Operation"
    _order = "id desc"

    name = fields.Char(string="Clearance No.", required=True, copy=False, default=lambda self: _("New"), index=True)

    waybill_id = fields.Many2one("world.depot.waybill", string="Waybill", required=True, ondelete="restrict", index=True)

    waybill_bill_number = fields.Char(string="Waybill Bill Number", compute="_compute_waybill_bill_number", store=True)

    @api.depends("waybill_id.bl_number", "waybill_id.hbl_number", "waybill_id.obl_number")
    def _compute_waybill_bill_number(self):
        for rec in self:
            rec.waybill_bill_number = rec.waybill_id.bl_number or rec.waybill_id.hbl_number or rec.waybill_id.obl_number

    clearance_type = fields.Selection(
        [
        ('general', 'General Trade'),
         ('bonded_in', 'Bonded In'),
         ('bonded_out', 'Bonded Out'),
         ('t1_transit', 'T1 Transit'),
         ('t1_bonded', 'T1 Bonded')], string="Clearance Type", default='general',
        required=True)

    eu_eori_no = fields.Char(string="EORI No", related="waybill_id.consignee.eu_eori_no", store=True, readonly=True)
    vat_tax_no = fields.Char(string="VAT No", related="waybill_id.consignee.vat", store=True, readonly=True)
    clearance_receipt_no = fields.Char(string="Customs Clearance Receipt No.", index=True, copy=False, tracking=True)

    customs_declaration_datetime = fields.Datetime(string="Customs Declaration Date",default=fields.Datetime.now, tracking=True)

    customs_release_datetime = fields.Datetime(string="Customs Release Date")
    inbound_release_datetime = fields.Datetime(string="Inbound Bonded Release Date")
    outbound_release_datetime = fields.Datetime(string="Outbound Bonded Release Date")
    t1_closed_datetime = fields.Datetime(string="T1 Closed Date")
    t1_inbound_release_datetime = fields.Datetime(string="T1 Inbound Release Date")

    can_complete = fields.Boolean(compute="_compute_can_complete", store=True)
    clearance_finish_datetime = fields.Datetime(string="Clearance Finish Time", compute='_compute_can_complete', store=True)


    external_system_type = fields.Selection([("tms", "TMS"), ("oms", "OMS"), ("other", "Other")], string="External System Type")
    external_system_no = fields.Char(string="External Order No.", index=True)
    sync_time = fields.Datetime(string="Sync Time")

    project_id = fields.Many2one("project.project", string="Project", related="waybill_id.project", store=True, readonly=True, index=True)



    state = fields.Selection(
        CLEARANCE_STATE,
        string="Status", default="open", required=True, tracking=True, index=True)
    statement_period_id = fields.Many2one("statement.period", string="Statement Period")
    statement_period_id_state = fields.Selection([], string="Statement Period State",
                                                 related="statement_period_id.state", store=True)
    handover_id = fields.Many2one("operation.order.handover", string="Handover")

    shipping_line_id = fields.Many2one("res.partner",related="waybill_id.shipping", string="Shipping Line")
    voyage_no = fields.Char(string="Voyage No.", index=True)
    shipper = fields.Many2one("res.partner", related='waybill_id.shipper', string="Shipper/Exporter")#装
    consignee = fields.Many2one("res.partner",related='waybill_id.consignee', string="Consignee/Importer")#卸
    terminal_a = fields.Many2one("res.partner", related="waybill_id.terminal_a", string="Terminal of Arrival")#交
    eta = fields.Date(string="ETA", related="waybill_id.eta")
    ata = fields.Date(string='ATA', related="waybill_id.ata")


    remark = fields.Text(string="Remark")

    #container_line_ids = fields.One2many("", "waybill_id", string="Containers", related="waybill_id.container_ids", readonly=True)

    container_qty = fields.Integer(string="Container Qty")
    hs_code_qty = fields.Integer(string='HS Code Qty')
    clearance_container_line_ids = fields.One2many("operation.order.clearance.container.line", "clearance_id", string="Containers", copy=False)
    container_line_ids = fields.One2many("world.depot.waybill.container", "waybill_id", string="Containers",
                                         related="waybill_id.container_ids", readonly=True)
    clearance_container_ids = fields.Many2many(
        "world.depot.waybill.container",
        "operation_order_clearance_container_rel",
        "clearance_id",
        "container_id",
        string="Clearance Containers",
    )
    invoice_line_ids = fields.One2many("operation.order.clearance.invoice.line", "clearance_id", string="Vendor Invoice Lines", copy=False)

    attachment_line_ids = fields.One2many("operation.order.clearance.attachment.line", "clearance_id", string="Document Lines")


    has_advance_invoice = fields.Boolean(string="Has Advance Invoice", compute="_compute_payment_summary", store=True)
    has_unpaid_advance_invoice = fields.Boolean(string="Has Unpaid Advance Invoice", compute="_compute_payment_summary", store=True)
    all_advance_paid = fields.Boolean(string="All Advance Paid", compute="_compute_payment_summary", store=True)

    # 费用明细
    charge_line_ids = fields.One2many("operation.order.clearance.charge.line", "clearance_id", string="Charges", copy=False)
    cost_line_ids = fields.One2many("operation.order.clearance.cost.line", "clearance_id", string="Costs", copy=False)
    currency_id = fields.Many2one("res.currency", string="Currency", related="waybill_id.quotation_id.currency_id",
                                  store=True)

    container_nums = fields.Char(string="Container Nums", compute="_compute_container_nums")

    amount_total_change = fields.Monetary(string="Total Amount", currency_field="currency_id",
                                          compute="_compute_amount_total_change")

    manual_amount_total_change = fields.Monetary(string="Manual Total Amount", currency_field="currency_id",
                                                 default=0.0,
                                                 tracking=True)

    parent_id = fields.Many2one("operation.order.clearance", string=" Partner Operation", index=True)
    extra_reason = fields.Selection([('customs_inspection', 'Customs Inspection'),
                                     ('detention', 'Detention'),
                                     ('split_container', 'Split Container'),
                                     ('clearance_exception', 'Clearance Exception'),
                                     ('service_add', 'Additional Service'),
                                     ('other', 'Other')],
                                    string="Additional Reason")

    actual_datetime = fields.Datetime(string="Actual Date")
    extra_remark = fields.Char(string="Additional Remark")

    reclearance_count = fields.Integer(string="Re-Clearance Count", default=0, copy=False, tracking=True)
    reclearance_reason = fields.Text(string="Last Re-Clearance Reason", copy=False, tracking=True)
    reclearance_user_id = fields.Many2one("res.users", string="Last Re-Clearance User", copy=False, readonly=True)
    reclearance_time = fields.Datetime(string="Last Re-Clearance Time", copy=False, readonly=True)

    # 逾期字段
    is_clearance_overdue = fields.Boolean(string="Is Clearance Overdue", compute="_compute_is_clearance_overdue",default=False)
    overdue_blocking_reason_id = fields.Many2one("operation.blocking.reason", string="Overdue Blocking Reason",
                                                 index=True, copy=False, tracking=True)
    overdue_reason_note = fields.Text(string="Overdue Reason Note", tracking=True, copy=False)
    overdue_blocking_reason_short_name = fields.Char(string="Overdue Blocking Reason Short Name",
                                                     related="overdue_blocking_reason_id.short_name", store=True)
    overdue_handle_result = fields.Selection([
        ("backfill_done", "Backfilled Clearance Done"),
        ("urge_customer_tax", "Urged Customer Tax/Documents"),
        ("follow_customs", "Followed Up Customs Inspection/Valuation"),
        ("follow_broker", "Followed Up Broker Fix"),
        ("other", "Other"),
    ], string="Overdue Handle Result", index=True, copy=False, tracking=True)
    overdue_result_note = fields.Text(string="Overdue Handle Note", copy=False, tracking=True)


    @api.onchange(
        "clearance_receipt_no",
        "customs_release_datetime",
        "inbound_release_datetime",
        "outbound_release_datetime",
        "t1_closed_datetime",
        "t1_inbound_release_datetime",
        "attachment_line_ids",
    )
    def onchange_customs_release_document_required(self):
        self.check_customs_release_document_required()

    @api.constrains(
        "clearance_receipt_no",
        "customs_release_datetime",
        "inbound_release_datetime",
        "outbound_release_datetime",
        "t1_closed_datetime",
        "t1_inbound_release_datetime",
        "attachment_line_ids",
    )
    def check_customs_release_document_required(self):
        for rec in self:
            has_release_info = bool(
                rec.clearance_receipt_no
                or rec.customs_release_datetime
                or rec.inbound_release_datetime
                or rec.outbound_release_datetime
                or rec.t1_closed_datetime
                or rec.t1_inbound_release_datetime
            )
            if not has_release_info:
                continue

            customs_release_files = rec.attachment_line_ids.filtered(
                lambda line: line.doc_type == "customs_release" and line.file
            )
            if not customs_release_files:
                raise ValidationError(
                    _("Customs release document is required when clearance finish time or release number is filled.")
                )

    @api.constrains("overdue_blocking_reason_id", "overdue_reason_note", "overdue_handle_result", "overdue_result_note")
    def check_handover_overdue_other_notes(self):
        for rec in self:
            reason_code = rec.overdue_blocking_reason_id.short_name if rec.overdue_blocking_reason_id else False
            if reason_code == "Others + Exp" and not (rec.overdue_reason_note or "").strip():
                raise ValidationError(_("Reason Note is required when Blocking Reason is Others."))
            if rec.overdue_handle_result == "other" and not (rec.overdue_result_note or "").strip():
                raise ValidationError(_("Result Note is required when Handle Result is Other."))


    @api.depends("state", "waybill_id.ata", "waybill_id.eta","clearance_finish_datetime")
    def _compute_is_clearance_overdue(self):
        done_states = {"clearanced", "close", "cancelled"}
        now_dt = fields.Datetime.now()
        rule = self.env["operation.workbench.alert.rule"].get_rule_values(company_id=self.env.company.id)
        available_days = int(rule.get("clearance_available_days", 5))

        for rec in self:
            rec.is_clearance_overdue = False
            if rec.state == "cancelled":
                continue

            base_date = rec.waybill_id.ata or rec.waybill_id.eta
            if not base_date:
                continue
            base_date_value = fields.Date.to_date(base_date)
            base_dt = datetime.combine(base_date_value, time(23, 59, 59))
            clearance_due_datetime = base_dt + timedelta(days=available_days)
            compare_datetime = rec.clearance_finish_datetime or now_dt
            rec.is_clearance_overdue = compare_datetime >= clearance_due_datetime

    @api.constrains('parent_id', 'extra_reason', 'remark')
    def check_remark(self):
        for rec in self:
            if rec.parent_id and rec.extra_reason:
                if not rec.remark or len(rec.remark) < 10:
                    raise ValidationError(_("The remark for a sub-record must be at least 10 characters."))



    def action_create_child_clearance(self):
        self.ensure_one()
        if self.state != 'close':
            raise ValidationError(_("Clearance must be close before creating child clearance."))
        vals = self.copy_data()[0]

        child_count = self.env['operation.order.clearance'].search_count([
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
            "name": "Child Clearance",
            "res_model": "operation.order.clearance",
            "view_mode": "form",
            "views": [(self.env.ref("wd_iffm.view_operation_order_clearance_child_form").id, "form")],
            "res_id": child.id,
        }

    def action_create_child_clearance_workbench(self):
        env_clearance = self.env["operation.order.clearance"]
        for rec in self:
            if rec.parent_id:
                raise ValidationError(_("Only the main customs clearance can create sub-customs clearances."))

            child_count = env_clearance.sudo().search_count([("parent_id", "=", rec.id)]) + 1

            vals = {
                "waybill_id": rec.waybill_id.id,
                "parent_id": rec.id,
                "name": f"{rec.name}-{child_count}",
                "clearance_type": rec.clearance_type,
                "external_system_type": rec.external_system_type,
                "external_system_no": rec.external_system_no,
                "voyage_no": rec.voyage_no,
                "customs_declaration_datetime": rec.customs_declaration_datetime,
                "actual_datetime": rec.actual_datetime,
                "extra_reason": rec.extra_reason,
                "extra_remark": rec.extra_remark,
                "remark": rec.remark,
                "state": "open",
                "clearance_container_ids": [(6, 0, rec.clearance_container_ids.ids)],
                "attachment_line_ids": [
                    (0, 0, {"doc_type": line.doc_type, "remark": line.remark, "file": line.file, "name": line.name}) for
                    line in rec.attachment_line_ids],
                # "charge_line_ids": [(0, 0, {"charge_item_id": line.charge_item_id.id,
                #                             "charge_origin_type": line.charge_origin_type, "qty": line.qty,
                #                             "unit_price": line.unit_price,
                #                             "manual_amount_total": line.manual_amount_total, "remark": line.remark}) for
                #                     line in rec.charge_line_ids],
            }
            child = env_clearance.create(vals)

            return {
                "ok": True,
                "message": _("Child clearance created successfully."),
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
    def action_clearance_remove_from_statement_period(self):
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


    @api.depends('clearance_container_ids')
    def _compute_container_nums(self):
        for record in self:
            container_numbers = [line.container_number for line in record.container_line_ids]
            record.container_nums = ', '.join(container_numbers)


    # @api.constrains("waybill_id", "state")
    # def _constrain_unique_waybill(self):
    #     env_model = self.env["operation.order.clearance"]
    #     for rec in self:
    #         if rec.parent_id:
    #             continue
    #         if not rec.waybill_id:
    #             continue
    #         domain = [
    #             ("waybill_id", "=", rec.waybill_id.id),
    #             ("parent_id", "=", False),
    #             ("state", "!=", "cancelled"),
    #         ]
    #         if rec.id:
    #             domain.append(("id", "!=", rec.id))
    #
    #         count = env_model.sudo().search_count(domain)
    #         if count:
    #             raise ValidationError(
    #                 _("This waybill is already used by another active clearance order.")
    #             )

    def action_clearancing(self):
        for rec in self:
            if rec.state not in ("open", "paying", "paid"):
                raise ValidationError(_("Only Open/Paying/Paid can go to Clearancing."))
            # if rec.state not in ("paying", "paid"):
            #     raise ValidationError(_("Only Apply/Paying/Paid can go to Clearancing."))
            # if rec.has_advance_invoice and not rec.all_advance_paid:
            #     raise ValidationError(_("All advance invoices must be paid before Clearancing."))
            if not rec.customs_declaration_datetime:
                raise ValidationError(_("Customs declaration date is required."))
            if not rec.eu_eori_no and not rec.vat_tax_no:
                raise ValidationError(_("EU EORI No or VAT Tax No is required."))
            rec.write({"state": "clearancing"})

    @api.depends("clearance_type", "customs_release_datetime", "inbound_release_datetime",
                 "outbound_release_datetime", "t1_closed_datetime", "t1_inbound_release_datetime")
    def _compute_can_complete(self):
        for rec in self:

            rec.can_complete = False
            rec.clearance_finish_datetime = False
            if rec.clearance_type == 'general' and rec.customs_release_datetime:
                rec.can_complete = True
                rec.clearance_finish_datetime = rec.customs_release_datetime

            elif rec.clearance_type == 'bonded_in' and rec.inbound_release_datetime:
                rec.can_complete = True
                rec.clearance_finish_datetime = rec.inbound_release_datetime

            elif rec.clearance_type == 'bonded_out' and rec.outbound_release_datetime:
                rec.can_complete = True
                rec.clearance_finish_datetime = rec.outbound_release_datetime

            elif rec.clearance_type == 't1_transit' and rec.t1_closed_datetime:
                rec.can_complete = True
                rec.clearance_finish_datetime = rec.t1_closed_datetime

            elif rec.clearance_type == 't1_bonded' and rec.t1_inbound_release_datetime:
                rec.can_complete = True
                rec.clearance_finish_datetime = rec.t1_inbound_release_datetime

    def sync_waybill_custom_clearance(self):
        done_states = ("clearanced", "close")
        env_clearance = self.env["operation.order.clearance"]

        for waybill in self.mapped("waybill_id"):
            clearances = env_clearance.sudo().search([
                ("waybill_id", "=", waybill.id),
                ("state", "!=", "cancelled"),
                ("parent_id", "=", False),
            ])

            clearance_container_ids = clearances.mapped("clearance_container_ids").ids
            all_orders_done = bool(clearances) and all(rec.state in done_states for rec in clearances)
            all_containers_covered = bool(waybill.container_ids) and all(
                container.id in clearance_container_ids for container in waybill.container_ids
            )

            waybill.write({"custom_clearance": all_orders_done and all_containers_covered})

    def action_clearanced(self):
        for rec in self:
            if rec.state != "clearancing":
                raise ValidationError(_("Only Clearancing can be set to Clearanced."))
            if not rec.waybill_id.ata or not rec.waybill_id.terminal_id:
                raise ValidationError(_("Waybill ETA and Terminal of Arrival is required before Released."))
            if not rec.vat_tax_no and not rec.clearance_receipt_no and not rec.eu_eori_no:
                raise ValidationError(_("VAT Tax No, Clearance Receipt No, EU EORI No is required before Released."))
            if not rec.clearance_finish_datetime:
                raise ValidationError(_("Clearance Finish Date is required before Released."))

            rec.write({"state": "clearanced",})
            rec.sync_waybill_custom_clearance()

    def action_open_reclearance_wizard(self):
        self.ensure_one()
        if self.state != "clearancing":
            raise ValidationError(_("Only clearancing order can return to paid for re-clearance."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Re-Clearance"),
            "res_model": "clearance.reclearance.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_clearance_id": self.id,
            },
        }

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
                if rec.state != "clearanced":
                    raise ValidationError(_("Only Clearanced can be closed."))
                if len(rec.charge_line_ids) == 0:
                    raise ValidationError(_("Charges are required before Close."))
                #关闭前必须有发票行
                invoice_lines = rec.invoice_line_ids
                if not invoice_lines:
                    raise ValidationError(_("Vendor invoice lines are required before Close."))

                unpaid_lines = invoice_lines.filtered(lambda line: line.payment_state != "paid")
                if unpaid_lines:
                    raise ValidationError(_("All vendor invoice lines must be paid before Close."))
            rec.write({"state": "close"})

    def get_required_doc_count(self, doc_type):
        self.ensure_one()
        lines = self.attachment_line_ids.filtered(lambda l: l.doc_type == doc_type and l.file)
        return len(lines)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("operation.order.clearance") or _("New")
        return super().create(vals_list)

    # @api.onchange("waybill_id")
    # def _onchange_waybill_id(self):
    #     for rec in self:
    #         if rec.waybill_id:
    #             rec.clearance_container_ids = [(6, 0, rec.waybill_id.container_ids.ids)]
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
    #             }) for ln in rec.waybill_id.project.quotation_id.quotation_customs_lines]
    #
    #             rec.container_qty = rec.waybill_id.container_qty
    #             rec.attachment_line_ids = attachment_lines
    #             rec.charge_line_ids = charge_lines
    #         else:
    #             rec.container_qty = False
    #             rec.attachment_line_ids = [(5, 0, 0)]
    #             rec.charge_line_ids = [(5, 0, 0)]
    def action_recompute_state(self):
        for rec in self:
            if rec.state in ("clearancing", "clearanced", "close", "cancelled"):
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

    @api.depends("invoice_line_ids", "invoice_line_ids.payment_state")
    def _compute_payment_summary(self):
        for rec in self:
            lines = rec.invoice_line_ids
            states = set(lines.mapped("payment_state"))

            rec.has_advance_invoice = bool(lines)
            rec.has_unpaid_advance_invoice = bool(lines.filtered(lambda l: l.payment_state != "paid"))
            rec.all_advance_paid = bool(lines) and states == {"paid"}

class OperationOrderClearanceInvoiceLine(models.Model):
    _name = "operation.order.clearance.invoice.line"
    _description = "Handover Vendor Invoice Line"
    _order = "id desc"

    clearance_id = fields.Many2one("operation.order.clearance", string="Clearance", index=True)
    customs_broker_id = fields.Many2one("res.partner", string="Clearance broker", index=True)
    vendor_partner_id = fields.Many2one("res.partner", string="Vendor (Shipping Line / Agent)",
                                        related='clearance_id.shipping_line_id', ondelete="restrict", store=True, index=True)
    vendor_invoice_id = fields.Many2one("account.move", string="Vendor Invoice (Optional)", ondelete="set null",
                                        index=True)
    invoice_date = fields.Date(string="Invoice Date", required=True, default=fields.Date.context_today)
    currency_id = fields.Many2one("res.currency", string="Currency", required=True, index=True,
                                  default=lambda self: self.default_currency_id())

    @api.model
    def default_currency_id(self):
        clearance_id = self.env.context.get("default_clearance_id")
        if clearance_id:
            clearance = self.env["operation.order.clearance"].sudo().browse(clearance_id)
            return clearance.currency_id.id
        return self.env.company.currency_id.id

    amount_total = fields.Monetary(string="Amount", currency_field="currency_id", compute="_compute_amount_total", store=True)

    payment_mode = fields.Selection([("advance", "Advance by Company"), ("customer_pay", "Paid by Customer")],
                                    string="Payment Mode", default="advance", required=True, index=True)
    payment_state = fields.Selection(
        [("draft", "Draft"), ("paying", "Paying"), ("paid", "Paid")],
        string="Payment State", default="draft", required=True, index=True)
    vendor_invoice_num = fields.Char(string="Vendor Invoice No")
    vendor_invoice_attachment_ids = fields.Many2many(
        "ir.attachment", "clearance_invoice_vendor_attachment_rel",
        "invoice_line_id", "attachment_id",
        string="Vendor Invoice Attachments", copy=False
    )
    bank_proof_attachment_ids = fields.Many2many(
        "ir.attachment", "clearance_invoice_bank_proof_attachment_rel",
        "invoice_line_id", "attachment_id", string="Bank Proof Attachments", copy=False)
    paid_user_id = fields.Many2one("res.users", string="Paid Confirmed By", readonly=True)
    paid_time = fields.Datetime(string="Paid Confirmed On", readonly=True)
    cost_line_ids = fields.One2many("operation.order.clearance.cost.line", "invoice_line_id", string="Cost Lines")
    remark = fields.Text(string="Remark")
    apply_user_id = fields.Many2one("res.users", string="Apply User", readonly=True, copy=False, index=True)
    apply_datetime = fields.Datetime(string="Apply Datetime", readonly=True, copy=False)
    # 会计对账

    payment_journal_id = fields.Many2one("account.journal", string="Payment Journal",
                                         domain=[("type", "in", ("bank", "cash"))])
    payment_id = fields.Many2one("account.payment", string="Payment", readonly=True)

    payment_company_id = fields.Many2one("res.partner", string="Payment Company",
                                         default=lambda self: self.default_payment_company_id(), index=True)
    receipt_company_id = fields.Many2one("res.partner", string="Receipt Company", index=True)

    @api.model
    def default_payment_company_id(self):
        clearance_id = self.env.context.get("default_clearance_id")
        if clearance_id:
            clearance = self.env["operation.order.clearance"].sudo().browse(clearance_id)
            return clearance.project_id.payment_company_id.id if clearance.project_id.payment_company_id else False
        return False

    @api.onchange("clearance_id")
    def onchange_clearance_id(self):
        for rec in self:
            if rec.clearance_id and not rec.payment_company_id:
                rec.payment_company_id = rec.clearance_id.project_id.payment_company_id

    @api.constrains("vendor_invoice_num")
    def check_vendor_invoice_num(self):
        for rec in self:
            if rec.vendor_invoice_num and self.search_count(
                    [("vendor_invoice_num", "=", rec.vendor_invoice_num), ("id", "!=", rec.id)]):
                raise ValidationError(_("Vendor Invoice No must be unique."))

    @api.constrains("vendor_invoice_attachment_ids", "amount_total")
    def check_vendor_invoice_attachment(self):
        for rec in self:
            if rec.vendor_invoice_attachment_ids and rec.amount_total <= 0:
                raise ValidationError(_("Amount must be greater than 0."))

    @api.depends("cost_line_ids.amount_total", "cost_line_ids.manual_amount_total")
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(
                (line.manual_amount_total if (line.manual_amount_total or 0.0) > 0 else (line.amount_total or 0.0))
                for line in rec.cost_line_ids
            )
    def action_request_clearance_payment(self):
        move_model = self.env["account.move"]
        for rec in self:
            if rec.clearance_id.is_clearance_overdue:
                if not rec.clearance_id.overdue_blocking_reason_id:
                    raise ValidationError(_("Overdue blocking reason is required for overdue handovers."))
                if not rec.clearance_id.overdue_handle_result:
                    raise ValidationError(_("Overdue handle result is required for overdue handovers."))
            operator = self.env.ref("base.user_admin")
            if not rec.cost_line_ids:
                raise ValidationError(_("Cost lines are required before requesting payment."))
            if rec.payment_mode != "advance":
                raise ValidationError(_("Only advance invoices can request payment."))
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
                [("type", "=", "purchase"), ("company_id", "=", rec.env.company.id), ('code', '=', 'BILL')], limit=1
            )
            if not journal:
                raise ValidationError(_("Purchase journal not found. Please configure a Purchase Journal."))

            if not rec.cost_line_ids:
                expense_account = (self.env["account.account"].sudo().search
                                   ([("account_type", "=", "expense"), ("company_ids", 'in', rec.env.company.id),
                                     ('code', '=', 'WDP400001')], limit=1))
                if not expense_account:
                    raise ValidationError(
                        _("Fallback account not found. Please configure it (code=WDP400001)."))
                line_name = _("Handover Bill - %s") % (rec.clearance_id.name,)
                invoice_lines = [(0, 0, {
                    "name": line_name,
                    "quantity": 1.0,
                    "price_unit": rec.amount_total or 0.0,
                    "account_id": expense_account.id,
                })]

            else:
                invoice_lines = []
                for cost in rec.cost_line_ids:
                    account = cost.charge_item_id.account_account_id
                    if not account:
                        raise ValidationError(
                            _("Account not found for charge item %s.") % (cost.charge_item_id.item_name,))
                    price = cost.manual_amount_total if cost.manual_amount_total>0 else cost.amount_total
                    name = _("Clearance Bill - %s") % (cost.charge_item_id.item_name,)
                    invoice_lines.append((0, 0, {
                        "name": name,
                        "quantity": cost.qty or 1.0,
                        "price_unit": price or 0.0,
                        "account_id": account.id,
                    }))
            waybill = rec.clearance_id.waybill_id
            waybill_bill_number = waybill.bl_number or waybill.hbl_number or waybill.obl_number or False

            move_vals = {
                "move_type": "in_invoice",
                "partner_id": rec.receipt_company_id.id,
                "invoice_date": rec.invoice_date or fields.Date.context_today(rec),
                "currency_id": rec.currency_id.id,
                "journal_id": journal.id,
                "ref": f"{rec.clearance_id.name}/{rec.id}",
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


            move.with_user(operator).action_post()
            rec.write({
                "vendor_invoice_id": move.id,
                "payment_state": "paying",
            })
        self.mapped("clearance_id").action_recompute_state()
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

        self.mapped("clearance_id").action_recompute_state()
        view_xmlid = "wd_iffm.operation_order_clearance_invoice_line_form_view"
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
            if rec.payment_state in ("paid"):
                raise ValidationError(_("Cannot delete invoice line that is already paid."))

            if rec.vendor_invoice_id:
                if rec.vendor_invoice_id.state == "posted":
                    raise ValidationError(_("Cannot delete invoice line linked to a posted vendor bill."))
                raise ValidationError(
                    _("This invoice line is linked to a vendor bill. "
                      "Please delete or cancel the vendor bill first.")
                )

        return super().unlink()


