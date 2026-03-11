# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OperationOrderClearance(models.Model):
    _name = "operation.order.clearance"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Clearance Operation"
    _order = "id desc"

    name = fields.Char(string="Clearance No.", required=True, copy=False, default=lambda self: _("New"), index=True)

    waybill_id = fields.Many2one("world.depot.waybill", string="Waybill", required=True, ondelete="restrict", index=True)

    clearance_type = fields.Selection(
        [
        ('general', 'General Trade'),
         ('bonded_in', 'Bonded In'),
         ('bonded_out', 'Bonded Out'),
         ('t1_transit', 'T1 Transit'),
         ('t1_bonded', 'T1 Bonded')], string="Clearance Type", default='general',
        required=True)
    #外部系统



    customs_release_datetime = fields.Datetime(string="Customs Release Date")
    inbound_release_datetime = fields.Datetime(string="Inbound Bonded Release Date")
    outbound_release_datetime = fields.Datetime(string="Outbound Bonded Release Date")
    t1_closed_datetime = fields.Datetime(string="T1 Closed Date")
    t1_inbound_release_datetime = fields.Datetime(string="T1 Inbound Release Date")

    can_complete = fields.Boolean(compute="_compute_can_complete")
    clearance_finish_datetime = fields.Datetime(string="Clearance Finish Time", compute='_compute_can_complete')


    external_system_type = fields.Selection([("tms", "TMS"), ("oms", "OMS"), ("other", "Other")], string="External System Type")
    external_system_no = fields.Char(string="External Order No.", index=True)
    sync_time = fields.Datetime(string="Sync Time")

    project_id = fields.Many2one("project.project", string="Project", related="waybill_id.project", store=True, readonly=True, index=True)



    state = fields.Selection(
        [("open", "Open"),
         ("paying", "Paying"), ("paid", "Paid"), ("clearancing", "Clearance"),
         ("clearanced", "Clearanced"), ("close", "Close"),
         ("cancelled", "Cancelled")],
        string="Status", default="open", required=True, tracking=True, index=True)
    statement_period_id = fields.Many2one("statement.period", string="Statement Period")
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
    #container_line_ids = fields.One2many("operation.order.clearance.container.line", "clearance_id", string="Containers", copy=False)
    container_line_ids = fields.One2many("world.depot.waybill.container", "waybill_id", string="Containers",
                                         related="waybill_id.container_ids", readonly=True)
    invoice_line_ids = fields.One2many("operation.order.clearance.invoice.line", "clearance_id", string="Vendor Invoice Lines", copy=False)

    attachment_line_ids = fields.One2many("operation.order.clearance.attachment.line", "clearance_id", string="Document Lines", copy=False)


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
    statement_period_id_state = fields.Selection([], string="Statement Period State", related="statement_period_id.state", store=True)
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


    @api.depends('container_line_ids')
    def _compute_container_nums(self):
        for record in self:
            container_numbers = [line.container_number for line in record.container_line_ids]
            record.container_nums = ', '.join(container_numbers)


    @api.constrains("waybill_id", "state")
    def _constrain_unique_waybill(self):
        env_model = self.env["operation.order.clearance"]
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
                    _("This waybill is already used by another active clearance order.")
                )

    def action_clearancing(self):
        for rec in self:
            if rec.state not in ("paying", "paid"):
                raise ValidationError(_("Only Apply/Paying/Paid can go to Clearancing."))
            if rec.has_advance_invoice and not rec.all_advance_paid:
                raise ValidationError(_("All advance invoices must be paid before Clearancing."))
            rec.write({"state": "clearancing"})

    @api.depends("clearance_type", "customs_release_datetime", "inbound_release_datetime",
                 "outbound_release_datetime", "t1_closed_datetime", "t1_inbound_release_datetime")
    def _compute_can_complete(self):
        for rec in self:

            rec.can_complete = False

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

    def action_clearanced(self):
        for rec in self:
            if rec.state != "clearancing":
                raise ValidationError(_("Only Clearancing can be set to Clearanced."))
            if not rec.waybill_id.ata or not rec.waybill_id.terminal_a:
                raise ValidationError(_("Waybill ETA and Terminal of Arrival is required before Released."))
            # if rec.get_required_doc_count("do") == 0:
            #     raise ValidationError(_("DO / Telex Release document is required before Released."))
            rec.write({"state": "clearanced",})
            rec.waybill_id.write({
                "custom_clearance": True
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
                if rec.state != "clearanced":
                    raise ValidationError(_("Only Clearanced can be closed."))
                if len(rec.charge_line_ids) == 0:
                    raise ValidationError(_("Charges are required before Close."))
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

    @api.onchange("waybill_id")
    def _onchange_waybill_id(self):
        for rec in self:
            if rec.waybill_id:
                rec.attachment_line_ids = [(5, 0, 0)]
                rec.charge_line_ids = [(5, 0, 0)]
                attachment_lines = [(0, 0, {
                    "doc_type": ln.bill_doc_type,
                    "remark": ln.description,
                    "file": ln.file,
                    "name": ln.filename,
                }) for ln in rec.waybill_id.other_docs_ids]

                charge_lines = [(0, 0, {
                    "charge_item_id": ln.charge_item_id.id,
                    "charge_origin_type": 'quotation',
                    "unit_price": ln.unit_price,
                }) for ln in rec.waybill_id.project.quotation_id.quotation_customs_lines]

                rec.container_qty = rec.waybill_id.container_qty
                rec.attachment_line_ids = attachment_lines
                rec.charge_line_ids = charge_lines
            else:
                rec.container_qty = False
                rec.attachment_line_ids = [(5, 0, 0)]
                rec.charge_line_ids = [(5, 0, 0)]
    def action_recompute_state(self):
        for rec in self:
            if rec.state in ("clearancing", "clearanced", "close", "cancelled"):
                continue
            if rec.has_advance_invoice:
                rec.write({"state": "paid" if rec.all_advance_paid else "paying"})

    @api.depends("invoice_line_ids.payment_mode", "invoice_line_ids.payment_state")
    def _compute_payment_summary(self):
        for rec in self:
            advance_lines = rec.invoice_line_ids.filtered(
                lambda l: any(c.cost_nature == "at cost" for c in l.cost_line_ids)
            )
            rec.has_advance_invoice = bool(advance_lines)
            rec.has_unpaid_advance_invoice = bool(advance_lines.filtered(lambda l: l.payment_state != "paid"))
            rec.all_advance_paid = bool(advance_lines) and not rec.has_unpaid_advance_invoice

class OperationOrderClearanceInvoiceLine(models.Model):
    _name = "operation.order.clearance.invoice.line"
    _description = "Handover Vendor Invoice Line"
    _order = "id desc"

    clearance_id = fields.Many2one("operation.order.clearance", string="Clearance", index=True)
    vendor_partner_id = fields.Many2one("res.partner", string="Vendor (Shipping Line / Agent)",
                                        related='clearance_id.shipping_line_id', ondelete="restrict", store=True, index=True)
    vendor_invoice_id = fields.Many2one("account.move", string="Vendor Invoice (Optional)", ondelete="set null",
                                        index=True)
    invoice_date = fields.Date(string="Invoice Date", required=True, default=fields.Date.context_today)
    currency_id = fields.Many2one("res.currency", string="Currency", related="clearance_id.waybill_id.project.quotation_id.currency_id", store=True,
                                  readonly=True)

    amount_total = fields.Monetary(string="Amount", currency_field="currency_id")

    payment_mode = fields.Selection([("advance", "Advance by Company"), ("customer_pay", "Paid by Customer")],
                                    string="Payment Mode", default="advance", required=True, index=True)
    payment_state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed"), ("paying", "Paying"), ("paid", "Paid")],
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

    # 会计对账

    payment_journal_id = fields.Many2one("account.journal", string="Payment Journal",
                                         domain=[("type", "in", ("bank", "cash"))])
    payment_id = fields.Many2one("account.payment", string="Payment", readonly=True)

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

    def action_request_clearance_payment(self):
        move_model = self.env["account.move"]
        for rec in self:
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
                    name = _("Handover Bill - %s") % (cost.charge_item_id.item_name,)
                    invoice_lines.append((0, 0, {
                        "name": name,
                        "quantity": cost.qty or 1.0,
                        "price_unit": price or 0.0,
                        "account_id": account.id,
                    }))

            move_vals = {
                "move_type": "in_invoice",
                "partner_id": rec.clearance_id.shipping_line_id.id,
                "invoice_date": rec.invoice_date or fields.Date.context_today(rec),
                "currency_id": rec.currency_id.id,
                "journal_id": journal.id,
                "ref": f"{rec.clearance_id.name}/{rec.id}",
                "invoice_line_ids": invoice_lines,
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
        self.mapped("clearance_id").action_recompute_state()
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

