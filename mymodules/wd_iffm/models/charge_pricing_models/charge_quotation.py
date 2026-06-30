# -*- coding: utf-8 -*-
import base64
import io

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from odoo.addons.wd_iffm.models.charge_item_inherit  import TAB_CATEGORY_LIST

class ChargeQuotation(models.Model):
    _name = "charge.quotation"
    _description = "Charge Quotation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    _rec_name = "alias_name"

    name = fields.Char(string="Quotation No.", readonly=True, copy=False, default="", index=True)
    alias_name = fields.Char(string="Alias Name", required=True, default="Alias")
    is_active = fields.Boolean(string="Active", default=False, index=True, tracking=True)
    date = fields.Date(string="Quotation Date", required=True, default=fields.Date.context_today, tracking=True)
    effective_from = fields.Date(string="Effective From", required=True, index=True, tracking=True)
    effective_to = fields.Date(string="Effective To", index=True, tracking=True)
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
    )
    remark = fields.Text(string="Remark")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("expired", "Expired"),
        ],
        string="Status",
        default="draft",
        required=True,
        copy=False,
        readonly=True,
        tracking=True,
        index=True,
    )

    quotation_lines = fields.One2many(
        "charge.quotation.line",
        "quotation_id",
        string="Quotation Lines",
        copy=True,
    )
    quotation_thc_lines = fields.One2many(
        "charge.quotation.line",
        "quotation_id",
        string="THC Lines",
        domain=[("tab_category", "=", "thc")],
    )
    quotation_customs_lines = fields.One2many(
        "charge.quotation.line",
        "quotation_id",
        string="Customs Lines",
        domain=[("tab_category", "=", "customs")],
    )
    quotation_trucking_lines = fields.One2many(
        "charge.quotation.line",
        "quotation_id",
        string="Trucking Lines",
        domain=[("tab_category", "=", "trucking")],
    )
    quotation_wh_in_lines = fields.One2many(
        "charge.quotation.line",
        "quotation_id",
        string="WH Inbound Lines",
        domain=[("tab_category", "=", "wh_in")],
    )
    quotation_storage_lines = fields.One2many(
        "charge.quotation.line",
        "quotation_id",
        string="Storage Lines",
        domain=[("tab_category", "=", "storage")],
    )
    quotation_wh_out_lines = fields.One2many(
        "charge.quotation.line",
        "quotation_id",
        string="WH Outbound Lines",
        domain=[("tab_category", "=", "wh_out")],
    )
    quotation_wh_extra_lines = fields.One2many(
        "charge.quotation.line",
        "quotation_id",
        string="WH Extra Lines",
        domain=[("tab_category", "=", "wh_extra")],
    )
    quotation_wh_pack_lines = fields.One2many(
        "charge.quotation.line",
        "quotation_id",
        string="WH Packaging Lines",
        domain=[("tab_category", "=", "wh_pack")],
    )
    quotation_wh_monthly_lines = fields.One2many(
        "charge.quotation.line",
        "quotation_id",
        string="WH Monthly Lines",
        domain=[("tab_category", "=", "wh_monthly")],
    )
    quotation_wh_other_lines = fields.One2many(
        "charge.quotation.line",
        "quotation_id",
        string="WH Other Lines",
        domain=[("tab_category", "=", "wh_other")],
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "") == "":
                vals["name"] = self.env["ir.sequence"].next_by_code("charge.quotation") or ""
        records = super().create(vals_list)
        return records


    def action_set_active(self):
        for rec in self:
            if  not rec.quotation_lines:
                raise ValidationError(_("Quotation must have at least one line."))
            rec.write({"state": "active", "is_active": True})

    def action_set_draft(self):
        for rec in self:
            rec.write({"state": "draft", "is_active": False})

    def action_set_expired(self):
        for rec in self:
            rec.write({"state": "expired", "is_active": False})

    @api.constrains("effective_from", "effective_to")
    def check_effective_date(self):
        for rec in self:
            if rec.effective_to and rec.effective_from and rec.effective_to < rec.effective_from:
                raise ValidationError(_("Effective To must be >= Effective From."))


    def action_export_by_category(self):
        self.ensure_one()


        line_env = self.env["charge.quotation.line"].sudo()
        lines = line_env.search([("quotation_id", "=", self.id)], order="id")

        if not lines:
            raise UserError(_("No quotation lines to export."))


        field = line_env._fields.get("tab_category")
        selection = getattr(field, "selection", [])
        if callable(selection):
            selection = selection(line_env)
        tab_map = dict(selection or [])


        grouped = {}
        for line in lines:
            key = line.tab_category or "no_category"
            grouped.setdefault(key, line_env.browse())
            grouped[key] |= line


        try:
            import xlsxwriter
        except Exception as e:
            raise UserError(_("xlsxwriter not installed: %s") % e)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        ws = workbook.add_worksheet("Charge Quotation")


        fmt_title = workbook.add_format({
            "bold": True, "font_size": 14,
        })
        fmt_k = workbook.add_format({"bold": True})
        fmt_v = workbook.add_format({})
        fmt_group = workbook.add_format({
            "bold": True,
            "font_color": "white",
            "bg_color": "#5B87C9",
            "align": "left",
            "valign": "vcenter",
        })
        fmt_head = workbook.add_format({
            "bold": True,
            "bg_color": "#D9E2F3",
            "border": 1,
        })
        fmt_cell = workbook.add_format({
            "border": 1,
        })
        fmt_money = workbook.add_format({
            "border": 1,
            "num_format": "#,##0.00",
        })

        # 设置列宽
        ws.set_column("A:A", 45)
        ws.set_column("B:B", 12)
        ws.set_column("C:C", 12)
        ws.set_column("D:D", 12)
        ws.set_column("E:E", 12)
        ws.set_column("F:F", 12)
        ws.set_column("G:G", 12)
        ws.set_column("H:H", 12)
        ws.set_column("I:I", 12)

        row = 0


        ws.write(row, 0, "Quotation", fmt_title)
        row += 2

        # 主信息
        main_info = [
            ("Quotation No.", self.name or ""),
            ("Currency", self.currency_id.name or ""),
            ("Quotation Date", str(self.date) if self.date else ""),
            ("Effective From", str(self.effective_from) if self.effective_from else ""),
            ("Effective To", str(self.effective_to) if self.effective_to else ""),
            ("Status", self.state or ""),
        ]

        for k, v in main_info:
            ws.write(row, 0, k, fmt_k)
            ws.write(row, 1, v, fmt_v)
            row += 1

        row += 2


        headers = [
            "Charge Item", "Unit", "Quantity Rule", "Pricing Rule",
            "Fixed Fee", "Unit Price", "Currency", "Active", "Remark"
        ]

        for col_num, header in enumerate(headers):
            ws.write(row, col_num, header, fmt_head)

        row += 1


        for cat in grouped.keys():
            cat_label = tab_map.get(cat, cat)
            ws.merge_range(row, 0, row, 8, cat_label, fmt_group)
            row += 1

            for line in grouped[cat]:

                ws.write(row, 0, line.charge_item_id.display_name or "", fmt_cell)
                ws.write(row, 1, line.charge_item_id.unit_id.display_name if line.charge_item_id.unit_id else "",
                         fmt_cell)
                ws.write(row, 2, line.quantity_rule_id.display_name if line.quantity_rule_id else "", fmt_cell)
                ws.write(row, 3, line.rule_id.display_name if line.rule_id else "", fmt_cell)
                ws.write(row, 4, "Yes" if line.is_fixed_fee else "No", fmt_cell)
                ws.write_number(row, 5, line.unit_price or 0.0, fmt_money)
                ws.write(row, 6, line.currency_id.name or "", fmt_cell)
                ws.write(row, 7, "Active" if line.active else "Inactive", fmt_cell)
                ws.write(row, 8, line.remark or "", fmt_cell)
                row += 1

            row += 1

        workbook.close()
        output.seek(0)
        file_content = output.read()


        attachment = self.env["ir.attachment"].create({
            "name": f"{self.name or 'quotation'}.xlsx",
            "type": "binary",
            "datas": base64.b64encode(file_content),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })

        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

class ChargeQuotationLine(models.Model):
    _name = "charge.quotation.line"
    _description = "Charge Quotation Line"
    _order = "id desc"

    quotation_id = fields.Many2one("charge.quotation", string="Quotation", required=True, ondelete="cascade", index=True)
    charge_item_id = fields.Many2one(
        "world.depot.charge.item",
        string="Charge Item",
        required=True,
        index=True,
        options="{'no_create': True, 'no_open': True}",
    )
    tab_category = fields.Selection(
        TAB_CATEGORY_LIST,
        string="Tab Category",
        related="charge_item_id.tab_category",
        store=True,
        index=True,
    )

    is_fixed_fee = fields.Boolean(string="Fixed Fee", default=False)
    unit_price = fields.Monetary(string="Unit Price", required=True, default=0.0)
    unit_id = fields.Many2one('world.depot.charge.unit', string='Unit',related="charge_item_id.unit_id")

    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="quotation_id.currency_id",
        store=True,
        readonly=True,
    )
    remark = fields.Text(string="Remark")
    active = fields.Boolean(string="Active", default=True, index=True)

    _sql_constraints = [
        ("uniq_quotation_item", "unique(quotation_id, charge_item_id)", "Charge item already exists in this quotation."),
    ]

    @api.constrains("quotation_id", "tab_category", "charge_item_id")
    def check_item_not_duplicate(self):

        line_env = self.env["charge.quotation.line"].sudo()
        for rec in self:
            if not rec.quotation_id or not rec.charge_item_id:
                continue
            dup_cnt = line_env.search_count([
                ("quotation_id", "=", rec.quotation_id.id),
                ("tab_category", "=", rec.tab_category),
                ("charge_item_id", "=", rec.charge_item_id.id),
                ("id", "!=", rec.id),
            ])
            if dup_cnt:
                raise ValidationError(_("This expense item already exists in this classification tab of the current quotation and cannot be added repeatedly."))
