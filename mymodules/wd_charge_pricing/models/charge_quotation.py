# -*- coding: utf-8 -*-

import base64
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .charge_item import OPERATION_TYPE


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
    currency_id = fields.Many2one("res.currency", string="Currency", required=True)
    remark = fields.Text(string="Remark")
    state = fields.Selection([("draft", "Draft"), ("active", "Active"), ("expired", "Expired")], string="Status", default="draft", required=True, copy=False, readonly=True, tracking=True, index=True)
    quotation_lines = fields.One2many("charge.quotation.line", "quotation_id", string="Quotation Lines", copy=True)
    quotation_thc_lines = fields.One2many("charge.quotation.line", "quotation_id", string="THC Lines", domain=[("tab_category", "=", "handover")])
    quotation_customs_lines = fields.One2many("charge.quotation.line", "quotation_id", string="Customs Lines", domain=[("tab_category", "=", "clearance")])
    quotation_trucking_lines = fields.One2many("charge.quotation.line", "quotation_id", string="Trucking Lines", domain=[("tab_category", "=", "clearance")])
    quotation_wh_in_lines = fields.One2many("charge.quotation.line", "quotation_id", string="WH Inbound Lines", domain=[("tab_category", "=", "inbound")])
    quotation_storage_lines = fields.One2many("charge.quotation.line", "quotation_id", string="Storage Lines", domain=[("tab_category", "=", "clearance")])
    quotation_wh_out_lines = fields.One2many("charge.quotation.line", "quotation_id", string="WH Outbound Lines", domain=[("tab_category", "=", "outbound")])
    quotation_wh_extra_lines = fields.One2many("charge.quotation.line", "quotation_id", string="WH Extra Lines", domain=[("tab_category", "=", "clearance")])
    quotation_wh_pack_lines = fields.One2many("charge.quotation.line", "quotation_id", string="WH Packaging Lines", domain=[("tab_category", "=", "clearance")])
    quotation_wh_monthly_lines = fields.One2many("charge.quotation.line", "quotation_id", string="WH Monthly Lines", domain=[("tab_category", "=", "clearance")])
    quotation_wh_other_lines = fields.One2many("charge.quotation.line", "quotation_id", string="WH Other Lines", domain=[("tab_category", "=", "clearance")])

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name"):
                vals["name"] = self.env["ir.sequence"].next_by_code("charge.quotation") or ""
        return super().create(vals_list)

    def action_set_active(self):
        for rec in self:
            if not rec.quotation_lines:
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
            if rec.effective_from and rec.effective_to and rec.effective_to < rec.effective_from:
                raise ValidationError(_("Effective To must be >= Effective From."))

    def action_export_by_category(self):
        self.ensure_one()
        env_quotation_line = self.env["charge.quotation.line"]
        lines = env_quotation_line.sudo().search([("quotation_id", "=", self.id)], order="id")
        if not lines:
            raise UserError(_("No quotation lines to export."))
        field = env_quotation_line._fields.get("tab_category")
        selection = field.selection(env_quotation_line) if callable(field.selection) else field.selection
        category_names = dict(selection or [])
        grouped_lines = {}
        for line in lines:
            grouped_lines.setdefault(line.tab_category or "no_category", env_quotation_line.browse())
            grouped_lines[line.tab_category or "no_category"] |= line
        try:
            import xlsxwriter
        except ImportError as error:
            raise UserError(_("xlsxwriter not installed: %s") % error) from error
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        worksheet = workbook.add_worksheet("Charge Quotation")
        title_format = workbook.add_format({"bold": True, "font_size": 14})
        key_format = workbook.add_format({"bold": True})
        group_format = workbook.add_format({"bold": True, "font_color": "white", "bg_color": "#5B87C9", "align": "left", "valign": "vcenter"})
        header_format = workbook.add_format({"bold": True, "bg_color": "#D9E2F3", "border": 1})
        cell_format = workbook.add_format({"border": 1})
        money_format = workbook.add_format({"border": 1, "num_format": "#,##0.00"})
        worksheet.set_column("A:A", 45)
        worksheet.set_column("B:I", 12)
        row = 0
        worksheet.write(row, 0, "Quotation", title_format)
        row += 2
        for label, value in [("Quotation No.", self.name or ""), ("Currency", self.currency_id.name or ""), ("Quotation Date", str(self.date) if self.date else ""), ("Effective From", str(self.effective_from) if self.effective_from else ""), ("Effective To", str(self.effective_to) if self.effective_to else ""), ("Status", self.state or "")]:
            worksheet.write(row, 0, label, key_format)
            worksheet.write(row, 1, value)
            row += 1
        row += 2
        headers = ["Charge Item", "Unit", "Fixed Fee", "Unit Price", "Currency", "Active", "Remark"]
        for column, header in enumerate(headers):
            worksheet.write(row, column, header, header_format)
        row += 1
        for category, category_lines in grouped_lines.items():
            worksheet.merge_range(row, 0, row, len(headers) - 1, category_names.get(category, category), group_format)
            row += 1
            for line in category_lines:
                worksheet.write(row, 0, line.charge_item_id.display_name or "", cell_format)
                worksheet.write(row, 1, line.charge_item_id.unit_id.display_name if line.charge_item_id.unit_id else "", cell_format)
                worksheet.write(row, 2, "Yes" if line.is_fixed_fee else "No", cell_format)
                worksheet.write_number(row, 3, line.unit_price or 0.0, money_format)
                worksheet.write(row, 4, line.currency_id.name or "", cell_format)
                worksheet.write(row, 5, "Active" if line.active else "Inactive", cell_format)
                worksheet.write(row, 6, line.remark or "", cell_format)
                row += 1
            row += 1
        workbook.close()
        attachment = self.env["ir.attachment"].create({"name": "%s.xlsx" % (self.name or "quotation"), "type": "binary", "datas": base64.b64encode(output.getvalue()), "res_model": self._name, "res_id": self.id, "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"})
        return {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % attachment.id, "target": "self"}


class ChargeQuotationLine(models.Model):
    _name = "charge.quotation.line"
    _description = "Charge Quotation Line"
    _order = "id desc"

    quotation_id = fields.Many2one("charge.quotation", string="Quotation", required=True, ondelete="cascade", index=True)
    charge_item_id = fields.Many2one("world.depot.charge.item", string="Charge Item", required=True, ondelete="restrict", index=True)
    tab_category = fields.Selection(OPERATION_TYPE, string="Tab Category", index=True)
    is_fixed_fee = fields.Boolean(string="Fixed Fee", default=False)
    unit_price = fields.Monetary(string="Unit Price", required=True, default=0.0)
    unit_id = fields.Many2one("world.depot.charge.unit", string="Unit", related="charge_item_id.unit_id", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency", related="quotation_id.currency_id", store=True, readonly=True)
    remark = fields.Text(string="Remark")
    active = fields.Boolean(string="Active", default=True, index=True)

    _sql_constraints = [("uniq_quotation_item", "unique(quotation_id, tab_category, charge_item_id)", "Charge item already exists in this quotation tab.")]

    @api.constrains("quotation_id", "tab_category", "charge_item_id")
    def check_item_not_duplicate(self):
        env_quotation_line = self.env["charge.quotation.line"]
        for rec in self:
            if not rec.quotation_id or not rec.charge_item_id:
                continue
            duplicate_count = env_quotation_line.sudo().search_count([("quotation_id", "=", rec.quotation_id.id), ("tab_category", "=", rec.tab_category), ("charge_item_id", "=", rec.charge_item_id.id), ("id", "!=", rec.id)])
            if duplicate_count:
                raise ValidationError(_("This expense item already exists in this classification tab of the current quotation and cannot be added repeatedly."))
