# -*- coding: utf-8 -*-

import base64
import io
from collections import defaultdict
from datetime import timedelta

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SunriseMonthlyCategoryPalletReport(models.Model):
    _name = "sunrise.monthly.category.pallet.report"
    _description = "Sunrise Monthly Category Pallet Report"
    _order = "id desc"

    name = fields.Char(string="Name", compute="_compute_name", store=True, readonly=True, copy=False, index=True)
    month_from = fields.Date(string="Start Month", required=True, default=lambda self: fields.Date.context_today(self).replace(day=1), index=True)
    month_to = fields.Date(string="End Month", required=True, default=lambda self: fields.Date.context_today(self).replace(day=1), index=True)
    sunrise_product_category_name = fields.Char(string="Sunrise Product Category", copy=False, index=True)
    state = fields.Selection([("draft", "Draft"), ("done", "Done")], string="State", default="draft", required=True, readonly=True, copy=False, index=True)
    refreshed_by_id = fields.Many2one("res.users", string="Last Refreshed By", readonly=True, copy=False)
    refreshed_datetime = fields.Datetime(string="Last Refreshed At", readonly=True, copy=False, index=True)
    line_ids = fields.One2many("sunrise.monthly.category.pallet.report.line", "report_id", string="Monthly Category Pallet Lines", readonly=True, copy=False)

    @api.depends("month_from", "month_to", "sunrise_product_category_name")
    def _compute_name(self):
        for rec in self:
            name = "%s ~ %s" % (rec.month_from or "", rec.month_to or "")
            rec.name = "%s / %s" % (name, rec.sunrise_product_category_name) if rec.sunrise_product_category_name else name

    def action_refresh_report(self):
        env = self.env
        project_model = env["project.project"].sudo()
        move_line_model = env["stock.move.line"].sudo()
        product_model = env["product.product"].sudo()
        report_line_model = env["sunrise.monthly.category.pallet.report.line"]
        action = False
        sunrise_project = project_model.search([("name", "=", "SUNRISE")], limit=1)
        if not sunrise_project:
            raise ValidationError(_("SUNRISE project was not found."))

        for rec in self:
            month_from = rec.month_from.replace(day=1)
            month_to = rec.month_to.replace(day=1)
            if month_from > month_to:
                raise ValidationError(_("Start Month must not be later than End Month."))
            month_dates = []
            month_date = month_from
            while month_date <= month_to:
                month_dates.append(month_date)
                month_date = (month_date.replace(day=28) + timedelta(days=4)).replace(day=1)
            month_end = (month_to.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            lifecycle_result = move_line_model.get_package_lifecycle_data({
                "date_from": month_from,
                "date_to": month_end,
                "project_id": sunrise_project.id,
                "timezone": env.context.get("tz") or env.user.tz or "UTC",
            })
            product_ids = {event["product_id"] for package_data in lifecycle_result["package_lifecycle_data"] for event in package_data["events"]}
            product_category_map = {}
            for product in product_model.browse(list(product_ids)):
                product_category_map[product.id] = (product.product_tmpl_id.sunrise_product_category_name or "").strip() or "Uncategorized"
            category_filter = (rec.sunrise_product_category_name or "").strip()
            monthly_package_map = defaultdict(
                lambda: {"opening": set(), "inbound": set(), "outbound": set(), "closing": set(), "outbound_stock_days": {}, "closing_stock_days": {}}
            )
            category_names = set()
            for package_data in lifecycle_result["package_lifecycle_data"]:
                category_quantity_map = defaultdict(float)
                category_inbound_date_map = {}
                event_index = 0
                package_id = package_data["package_id"]
                events = package_data["events"]
                for month_date in month_dates:
                    next_month_date = (month_date.replace(day=28) + timedelta(days=4)).replace(day=1)
                    while event_index < len(events) and events[event_index]["event_date"] < month_date:
                        event = events[event_index]
                        category_name = product_category_map.get(event["product_id"], "Uncategorized")
                        quantity_before = category_quantity_map[category_name]
                        category_quantity_map[category_name] += event["quantity"]
                        if event["direction"] == "inbound" and event["picking_type_code"] == "incoming" and quantity_before <= 0.000001 and category_quantity_map[category_name] > 0.000001:
                            category_inbound_date_map[category_name] = event["event_date"]
                        if category_quantity_map[category_name] <= 0.000001:
                            category_inbound_date_map.pop(category_name, None)
                        event_index += 1
                    opening_categories = {category_name for category_name, quantity in category_quantity_map.items() if quantity > 0.000001}
                    inbound_categories = set()
                    outbound_categories = set()
                    while event_index < len(events) and events[event_index]["event_date"] < next_month_date:
                        event = events[event_index]
                        category_name = product_category_map.get(event["product_id"], "Uncategorized")
                        quantity_before = category_quantity_map[category_name]
                        category_quantity_map[category_name] += event["quantity"]
                        if event["direction"] == "inbound" and event["picking_type_code"] == "incoming":
                            inbound_categories.add(category_name)
                            if quantity_before <= 0.000001 and category_quantity_map[category_name] > 0.000001:
                                category_inbound_date_map[category_name] = event["event_date"]
                        if event["is_actual_outbound"]:
                            outbound_categories.add(category_name)
                            if quantity_before > 0.000001 and category_quantity_map[category_name] <= 0.000001 and category_inbound_date_map.get(category_name):
                                monthly_package_map[(month_date, category_name)]["outbound_stock_days"][package_id] = (event["event_date"] - category_inbound_date_map[category_name]).days
                        if category_quantity_map[category_name] <= 0.000001:
                            category_inbound_date_map.pop(category_name, None)
                        event_index += 1
                    closing_categories = {category_name for category_name, quantity in category_quantity_map.items() if quantity > 0.000001}
                    for category_name in opening_categories | inbound_categories | outbound_categories | closing_categories:
                        if category_filter and category_name != category_filter:
                            continue
                        category_names.add(category_name)
                        monthly_package_data = monthly_package_map[(month_date, category_name)]
                        if category_name in opening_categories:
                            monthly_package_data["opening"].add(package_id)
                        if category_name in inbound_categories:
                            monthly_package_data["inbound"].add(package_id)
                        if category_name in outbound_categories:
                            monthly_package_data["outbound"].add(package_id)
                        if category_name in closing_categories:
                            monthly_package_data["closing"].add(package_id)
                            inbound_date = category_inbound_date_map.get(category_name)
                            if inbound_date:
                                monthly_package_data["closing_stock_days"][package_id] = (next_month_date - timedelta(days=1) - inbound_date).days
            line_values_list = []
            for month_date in month_dates:
                for category_name in sorted(category_names):
                    package_data = monthly_package_map[(month_date, category_name)]
                    line_values_list.append({
                        "report_id": rec.id,
                        "month_date": month_date,
                        "sunrise_product_category_name": category_name,
                        "opening_pallet_count": len(package_data["opening"]),
                        "inbound_pallet_count": len(package_data["inbound"]),
                        "outbound_pallet_count": len(package_data["outbound"]),
                        "closing_pallet_count": len(package_data["closing"]),
                        "average_outbound_stock_days": sum(package_data["outbound_stock_days"].values()) / len(package_data["outbound_stock_days"]) if package_data["outbound_stock_days"] else 0.0,
                        "average_closing_stock_days": sum(package_data["closing_stock_days"].values()) / len(package_data["closing_stock_days"]) if package_data["closing_stock_days"] else 0.0,
                    })
            rec.line_ids.unlink()
            if line_values_list:
                report_line_model.create(line_values_list)
            rec.write({"state": "done", "refreshed_by_id": env.user.id, "refreshed_datetime": fields.Datetime.now()})
            action = {"type": "ir.actions.act_window", "name": _("Sunrise Monthly Category Pallet Report"), "res_model": rec._name, "view_mode": "form", "res_id": rec.id, "target": "current"}
        return action

    def action_export_excel(self):
        env = self.env
        report_line_model = env["sunrise.monthly.category.pallet.report.line"].sudo()
        attachment_model = env["ir.attachment"]
        action = False
        for rec in self:
            if rec.state != "done":
                raise ValidationError(_("Please refresh the report before exporting."))
            report_lines = report_line_model.search([("report_id", "=", rec.id)], order="month_date asc, sunrise_product_category_name asc, id asc")
            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output, {"in_memory": True})
            worksheet = workbook.add_worksheet("Monthly Category Pallets")
            title_format = workbook.add_format({"bold": True, "font_size": 14, "align": "center", "valign": "vcenter"})
            header_format = workbook.add_format({"bold": True, "align": "center", "valign": "vcenter", "text_wrap": True, "bg_color": "#D9EAF7", "border": 1})
            text_format = workbook.add_format({"border": 1, "valign": "vcenter"})
            number_format = workbook.add_format({"border": 1, "valign": "vcenter", "align": "right", "num_format": "0"})
            stock_days_format = workbook.add_format({"border": 1, "valign": "vcenter", "align": "right", "num_format": "0.00"})
            headers = ["Month", "Product Category", "Opening Pallets", "Inbound Pallets", "Outbound Pallets", "Closing Pallets", "Average Outbound Stock Days", "Average Closing Stock Days"]
            worksheet.merge_range(0, 0, 0, len(headers) - 1, "%s - %s" % (_("Sunrise Monthly Category Pallet Report"), rec.name or ""), title_format)
            worksheet.write_row(2, 0, headers, header_format)
            for row_index, line in enumerate(report_lines, start=3):
                worksheet.write(row_index, 0, fields.Date.to_string(line.month_date) if line.month_date else "", text_format)
                worksheet.write(row_index, 1, line.sunrise_product_category_name or "Uncategorized", text_format)
                worksheet.write_number(row_index, 2, line.opening_pallet_count, number_format)
                worksheet.write_number(row_index, 3, line.inbound_pallet_count, number_format)
                worksheet.write_number(row_index, 4, line.outbound_pallet_count, number_format)
                worksheet.write_number(row_index, 5, line.closing_pallet_count, number_format)
                worksheet.write_number(row_index, 6, line.average_outbound_stock_days, stock_days_format)
                worksheet.write_number(row_index, 7, line.average_closing_stock_days, stock_days_format)
            worksheet.freeze_panes(3, 0)
            worksheet.autofilter(2, 0, max(2, len(report_lines) + 2), len(headers) - 1)
            worksheet.set_column(0, 0, 14)
            worksheet.set_column(1, 1, 28)
            worksheet.set_column(2, 7, 22)
            workbook.close()
            attachment = attachment_model.create({
                "name": "Sunrise_Monthly_Category_Pallet_Report_%s.xlsx" % (rec.name or rec.id),
                "type": "binary",
                "datas": base64.b64encode(output.getvalue()),
                "res_model": rec._name,
                "res_id": rec.id,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            })
            action = {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % attachment.id, "target": "self"}
        return action


class SunriseMonthlyCategoryPalletReportLine(models.Model):
    _name = "sunrise.monthly.category.pallet.report.line"
    _description = "Sunrise Monthly Category Pallet Report Line"
    _order = "month_date asc, sunrise_product_category_name asc, id asc"

    report_id = fields.Many2one("sunrise.monthly.category.pallet.report", string="Report", required=True, readonly=True, ondelete="cascade", index=True, copy=False)
    month_date = fields.Date(string="Month", required=True, readonly=True, index=True, copy=False)
    sunrise_product_category_name = fields.Char(string="Sunrise Product Category", required=True, readonly=True, index=True, copy=False)
    opening_pallet_count = fields.Integer(string="Opening Pallets", required=True, readonly=True, copy=False)
    inbound_pallet_count = fields.Integer(string="Inbound Pallets", required=True, readonly=True, copy=False)
    outbound_pallet_count = fields.Integer(string="Outbound Pallets", required=True, readonly=True, copy=False)
    closing_pallet_count = fields.Integer(string="Closing Pallets", required=True, readonly=True, copy=False)
    average_outbound_stock_days = fields.Float(string="Average Outbound Stock Days", required=True, readonly=True, digits=(16, 2), copy=False)
    average_closing_stock_days = fields.Float(string="Average Closing Stock Days", required=True, readonly=True, digits=(16, 2), copy=False)
