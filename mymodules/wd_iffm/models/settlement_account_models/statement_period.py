from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import io
import base64
import xlsxwriter


class StatementPeriod(models.Model):
    _name = "statement.period"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Statement Period"

    name = fields.Char(string="Statement No", required=True, copy=False, default=lambda self: _("New"), index=True)
    date_start = fields.Date(string="Start Date", required=True)
    date_end = fields.Date(string="End Date", required=True)
    project_id = fields.Many2one('project.project', string="Project", required=True)

    statement_time_type = fields.Selection([
        ('eta', 'ETA Time'),
        ('finish', 'Finish Time')
    ], string="Statement Time Type", default='finish', required=True)

    operation_order_scope = fields.Selection([
        ('master', 'Master Order'),
        ('child', 'Child Order'),
        ('both', 'Master & Child')
    ], string="Operation Order Scope", default='both', required=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('expense_confirmed', 'Expense Confirmed'),
        ('payment_in_progress', 'Payment In Progress'),
        ('calculated', 'Calculated'),
        ('cancelled', 'Cancelled'),
    ], string="State", default='draft', required=True, track_visibility='onchange')

    expense_confirmed_datetime = fields.Datetime(string="Expense Confirmed Date")
    handover_order_lines = fields.One2many('operation.order.handover', 'statement_period_id', ondelete='set null', string="Handover Orders")
    clearance_order_lines = fields.One2many('operation.order.clearance', 'statement_period_id', ondelete='set null',
                                            string="Clearance Orders")

    handover_total_amount = fields.Monetary(string="Total Handover Amount", currency_field='currency_id', compute="_compute_handover_amount")
    clearance_total_amount = fields.Monetary(string="Total Clearance Amount", currency_field='currency_id', compute="_compute_clearance_amount")

    # 汇总用币种
    currency_id = fields.Many2one('res.currency', related='project_id.quotation_id.currency_id', store=True,string='Currency')
    customer_invoice_id = fields.Many2one('account.move', string="Customer Invoice")
    customer_invoice_attachment_ids = fields.Many2many(
        "ir.attachment",
        "statement_period_customer_invoice_attach_rel",
        "statement_period_id",
        "attachment_id",
        string="Customer Invoice Files",
        copy=False,
    )

    @api.depends("customer_invoice_id.state", "customer_invoice_id.payment_state", "customer_invoice_id.move_type")
    def _compute_invoice_status(self):
        for rec in self:
            if rec.customer_invoice_id.payment_state == "paid":
                rec.state = "calculated"

    def action_confirm_expense(self):
        for period in self:
            period.write({'state': 'expense_confirmed',
                          'expense_confirmed_datetime': fields.Datetime.now(),})

    def action_draft(self):
        for period in self:
            period.write({'state': 'draft'})

    @api.depends('handover_order_lines')
    def _compute_handover_amount(self):
        for period in self:
            handover_total = 0.0
            for line in period.handover_order_lines:
                amount = line.manual_amount_total_change if line.manual_amount_total_change > 0 else line.amount_total_change
                handover_total += amount
            period.handover_total_amount = handover_total

    @api.depends('clearance_order_lines')
    def _compute_clearance_amount(self):
        for period in self:
            clearance_total = 0.0
            for line in period.clearance_order_lines:
                for charge_line in line.charge_line_ids:
                    amount = charge_line.manual_amount_total if charge_line.manual_amount_total > 0 else charge_line.amount_total
                    clearance_total += amount
            period.clearance_total_amount = clearance_total

    def get_periodic_statement(self):
        env = self.env

        for rec in self:
            rec.handover_order_lines = [(5, 0, 0)]
            rec.clearance_order_lines = [(5, 0, 0)]
            handover_time_field = ''
            clearance_time_field = ''
            additional_time_field = ''
            if rec.statement_time_type == 'finish':
                if rec.operation_order_scope == 'child':
                    handover_time_field = 'actual_datetime'
                    clearance_time_field = 'actual_datetime'
                elif rec.operation_order_scope == 'master':
                    handover_time_field = 'do_issue_datetime'
                    clearance_time_field = 'clearance_finish_datetime'
                elif rec.operation_order_scope == 'both':
                    handover_time_field = 'do_issue_datetime'
                    clearance_time_field = 'clearance_finish_datetime'
                    additional_time_field = 'actual_datetime'
            else:
                handover_time_field = 'eta'
                clearance_time_field = 'eta'
                additional_time_field = 'eta'

            # 基础时间域
            base_domain = [('state', '=', 'close'),('project_id', '=', rec.project_id.id)]
            #base_domain = []

            handover_time_domain = [
                                       (handover_time_field, '>=', rec.date_start),
                                       (handover_time_field, '<=', rec.date_end),
                                   ] + base_domain

            clearance_time_domain = [
                                        (clearance_time_field, '>=', rec.date_start),
                                        (clearance_time_field, '<=', rec.date_end),
                                        ("state", "in", ("clearanced", "close")),('project_id', '=', rec.project_id.id)
                                    ]

            additional_time_domain = [
                                         (additional_time_field, '>=', rec.date_start),
                                         (additional_time_field, '<=', rec.date_end),
                                     ] + base_domain

            # handover_time_domain = []
            # clearance_time_domain = []
            # additional_time_domain = []
            handover_records = False
            clearance_records = False
            if rec.operation_order_scope == 'child':
                handover_records = env['operation.order.handover'].sudo().search(additional_time_domain + [('parent_id', '!=', False)])
                clearance_records = env['operation.order.clearance'].sudo().search(additional_time_domain + [('parent_id', '!=', False)])
            elif rec.operation_order_scope == 'master':
                handover_records = env['operation.order.handover'].sudo().search(
                    handover_time_domain + [('parent_id', '=', False)]
                )
                clearance_records = env['operation.order.clearance'].sudo().search(
                    clearance_time_domain + [('parent_id', '=', False)]
                )
            elif rec.operation_order_scope == 'both':
                handover_records = env['operation.order.handover'].sudo().search(handover_time_domain)
                clearance_records = env['operation.order.clearance'].sudo().search(clearance_time_domain)
                handover_records |= env['operation.order.handover'].sudo().search(additional_time_domain)
                clearance_records |= env['operation.order.clearance'].sudo().search(additional_time_domain)

            rec.handover_order_lines |= handover_records
            rec.clearance_order_lines |= clearance_records

            rec._compute_handover_amount()
            rec._compute_clearance_amount()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Statement Period"),
                "message": _("Statement Period generated successfully."),
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.client",
                    "tag": "reload",
                },
            },
        }



    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("statement.period") or _("New")
        return super().create(vals_list)

    def action_export_statement_xlsx(self):
        for rec in self:
            if rec.state == 'draft':
                raise ValidationError(_("Please confirm the expense first."))

            output = io.BytesIO()
            wb = xlsxwriter.Workbook(output, {"in_memory": True})

            formats = self.get_xlsx_formats(wb)

            self.build_handover_sheet(wb, rec, formats)
            self.build_clearance_sheet(wb, rec, formats)

            wb.close()
            output.seek(0)

            content = base64.b64encode(output.read())
            filename = f"Statement-{rec.name or rec.id}.xlsx"
            att = self.env["ir.attachment"].create({
                "name": filename,
                "type": "binary",
                "datas": content,
                "res_model": rec._name,
                "res_id": rec.id,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            })
            return {"type": "ir.actions.act_url", "url": f"/web/content/{att.id}?download=true", "target": "self"}

    # =====================
    # Formats
    # =====================
    def get_xlsx_formats(self, wb):
        base_font = {"font_name": "Arial", "font_size": 12}
        return {
            "header": wb.add_format({**base_font, "bold": True, "align": "center", "valign": "vcenter", "bg_color": "#B8860B", "border": 1}),
            "cell": wb.add_format({**base_font, "border": 1, "valign": "vcenter"}),
            "int": wb.add_format({**base_font, "border": 1, "valign": "vcenter", "align": "center", "num_format": "0"}),
            "money": wb.add_format({**base_font, "border": 1, "valign": "vcenter", "align": "right", "num_format": "_-€ * #,##0.00_-"}),
            "total_label": wb.add_format({**base_font, "bold": True, "align": "center", "valign": "vcenter", "bg_color": "#8BC34A", "border": 1}),
            "total_money": wb.add_format({**base_font, "bold": True, "align": "right", "valign": "vcenter", "bg_color": "#8BC34A", "border": 1, "num_format": "_-€ * #,##0.00_-"}),
            "total_blank": wb.add_format({**base_font, "bg_color": "#8BC34A", "border": 1}),
        }

    # Common helpers
    def amount_with_manual(self, charge_line):
        return (charge_line.manual_amount_total if (charge_line.manual_amount_total or 0.0) > 0 else charge_line.amount_total) or 0.0

    def collect_item_names(self, order_lines):
        names = set()
        for ln in order_lines:
            for cl in ln.charge_line_ids:
                if cl.charge_item_id and cl.charge_item_id.item_name:
                    names.add(cl.charge_item_id.item_name)
        return sorted(names)

    def sum_fee_by_item_name(self, order_line, item_name):
        fee_lines = order_line.charge_line_ids.filtered(lambda x: x.charge_item_id.item_name == item_name)
        return sum(self.amount_with_manual(x) for x in fee_lines)

    # =====================
    # Sheet 1: Handover
    # =====================
    def build_handover_sheet(self, wb, rec, fmt):
        ws = wb.add_worksheet("Terminal Handling (THC)")

        fixed_left = ["BL", "Container", "Shipping line", "Container amount"]
        fixed_right = ["Amount", "Note"]
        fee_cols = self.collect_item_names(rec.handover_order_lines)
        headers = fixed_left + fee_cols + fixed_right

        ws.set_column(0, 0, 12)
        ws.set_column(1, 1, 15)
        ws.set_column(2, 2, 20)
        ws.set_column(3, 3, 18)
        fee_start = len(fixed_left)
        if fee_cols:
            ws.set_column(fee_start, fee_start + len(fee_cols) - 1, 20)
        ws.set_column(len(headers) - 2, len(headers) - 2, 16)
        ws.set_column(len(headers) - 1, len(headers) - 1, 18)

        ws.write_row(0, 0, headers, fmt["header"])

        amount_col = len(headers) - 2
        note_col = len(headers) - 1
        row = 1
        total_amount = rec.handover_total_amount


        for l in rec.handover_order_lines:
            ws.write(row, 0, l.waybill_id.bl_number or l.waybill_id.hbl_number or l.waybill_id.obl_number, fmt["cell"])
            ws.write(row, 1, l.container_nums, fmt["cell"])
            ws.write(row, 2, l.shipping_line_id.name, fmt["cell"])
            ws.write_number(row, 3, l.container_qty, fmt["int"])

            line_total = 0.0
            for idx, fee_name in enumerate(fee_cols):
                col = fee_start + idx
                fee_amt = self.sum_fee_by_item_name(l, fee_name)
                ws.write_number(row, col, float(fee_amt), fmt["money"])
            line_total = l.manual_amount_total_change if (l.manual_amount_total_change or 0.0) > 0 else l.amount_total_change
            ws.write_number(row, amount_col, float(line_total), fmt["money"])
            ws.write(row, note_col, l.remark or "", fmt["cell"])


            row += 1

        ws.merge_range(row, 0, row, amount_col - 1, "Total amount", fmt["total_label"])
        ws.write_number(row, amount_col, float(total_amount), fmt["total_money"])
        ws.write_blank(row, note_col, None, fmt["total_blank"])

    # Sheet 2: Clearance
    def build_clearance_sheet(self, wb, rec, fmt):
        ws = wb.add_worksheet("Custom Clearance")

        fixed_left = ["B/L", "Container Number"]
        fixed_right = ["amount"]
        fee_cols = self.collect_item_names(rec.clearance_order_lines)
        headers = fixed_left + fee_cols + fixed_right

        ws.set_column(0, 0, 16)
        ws.set_column(1, 1, 20)
        fee_start = len(fixed_left)
        if fee_cols:
            ws.set_column(fee_start, fee_start + len(fee_cols) - 1, 18)
        ws.set_column(len(headers) - 1, len(headers) - 1, 16)

        ws.write_row(0, 0, headers, fmt["header"])

        amount_col = len(headers) - 1
        row = 1
        total_amount = rec.clearance_total_amount


        for c in rec.clearance_order_lines:
            ws.write(row, 0, c.waybill_id.bl_number or c.waybill_id.hbl_number or c.waybill_id.obl_number, fmt["cell"])
            ws.write(row, 1, c.container_nums, fmt["cell"])

            line_total = 0.0
            for idx, fee_name in enumerate(fee_cols):
                col = fee_start + idx
                fee_amt = self.sum_fee_by_item_name(c, fee_name)
                ws.write_number(row, col, float(fee_amt), fmt["money"])

            line_total = c.manual_amount_total_change if (c.manual_amount_total_change or 0.0) > 0 else c.amount_total_change
            ws.write_number(row, amount_col, float(line_total), fmt["money"])
            row += 1

        ws.merge_range(row, 0, row, amount_col - 1, "Total amount", fmt["total_label"])
        ws.write_number(row, amount_col, float(total_amount), fmt["total_money"])

    def request_invoice_customer(self):
        for period in self:
            invoice_lines = []
            if period.state != 'expense_confirmed':
                raise ValidationError(_("Please confirm the expense first."))
            if period.handover_total_amount == 0 or period.clearance_total_amount == 0:
                raise ValidationError(_("Please enter the amount for handover and clearance orders."))


            journal = self.env["account.journal"].sudo().search(
            [("type", "=", "sale"), ("company_id", "=", period.env.company.id), ('code', '=', 'INV')], limit=1
            )
            if not journal:
                raise ValidationError(_("Purchase journal not found. Please configure a Purchase Journal."))
            hanover_expense_account = (self.env["account.account"].sudo().search
                               ([("account_type", "=", "income"), ("company_ids", 'in', period.env.company.id),
                                 ('code', '=', 'WDA5001')], limit=1))

            invoice_lines.append((0, 0, {
                "name":  _("Total Handover Amount"),
                "quantity": 1.0,
                "price_unit": period.handover_total_amount or 0.0,
                "account_id": hanover_expense_account.id,
            }))

            clearance_expense_account = (self.env["account.account"].sudo().search
                               ([("account_type", "=", "income"), ("company_ids", 'in', period.env.company.id),
                                 ('code', '=', 'WDA5002')], limit=1))

            invoice_lines.append((0, 0, {
                "name": _("Total Clearance Amount"),
                "quantity": 1.0,
                "price_unit": period.clearance_total_amount or 0.0,
                "account_id": clearance_expense_account.id,
            }))
            invoice_vals = {
                'partner_id': period.project_id.partner_id.id,
                'currency_id': period.project_id.currency_id.id,
                'invoice_date': fields.Date.today(),
                "journal_id": journal.id,
                "ref": f"{period.name}/{period.id}",
                "move_type": "out_invoice",
                "invoice_line_ids": invoice_lines,
            }
            move =  self.env["account.move"].create(invoice_vals)

            move.action_post()
            period.write({
                "customer_invoice_id": move.id,
                "state": "payment_in_progress",
            })

        # self.mapped("handover_id").action_recompute_state()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Payment Requested"),
                "message": _("Customer Payment request has been submitted successfully."),
                "type": "success",
                "sticky": False,
            },
        }