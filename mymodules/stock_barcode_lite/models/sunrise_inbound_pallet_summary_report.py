# -*- coding: utf-8 -*-

import base64
import io

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SunriseInboundPalletSummaryReport(models.Model):
    _name = "sunrise.inbound.pallet.summary.report"
    _description = "Sunrise Inbound Pallet Summary Report"
    _order = "id desc"

    name = fields.Char(string="Name", compute="_compute_name", store=True, readonly=True, copy=False, index=True)
    date_from = fields.Date(string="Date From", required=True, default=lambda self: fields.Date.context_today(self).replace(day=1), index=True)
    date_to = fields.Date(string="Date To", required=True, default=fields.Date.context_today, index=True)
    location_scope = fields.Selection(selection="get_location_scope_selection", string="Location", copy=False, index=True)
    cprojectid = fields.Char(string="Contract No", copy=False, index=True)
    state = fields.Selection([("draft", "Draft"), ("done", "Done")], string="State", default="draft", required=True, readonly=True, copy=False, index=True)
    refreshed_by_id = fields.Many2one("res.users", string="Last Refreshed By", readonly=True, copy=False)
    refreshed_datetime = fields.Datetime(string="Last Refreshed At", readonly=True, copy=False, index=True)
    inbound_summary_lines = fields.One2many("sunrise.inbound.pallet.summary.report.line", "report_id", string="Inbound Summary Lines", readonly=True, copy=False)

    @api.model
    def get_location_scope_selection(self):
        project_model = self.env["project.project"].sudo()
        sunrise_project = project_model.search([("name", "=", "SUNRISE")], limit=1)
        if not sunrise_project or "portal_stock_location_line_ids" not in project_model._fields:
            return [("other", "Other")]
        locations = sunrise_project.mapped("portal_stock_location_line_ids").sorted(key=lambda location: (location.complete_name or location.display_name, location.id))
        return [("location_%s" % location.id, location.complete_name or location.display_name) for location in locations] + [("other", "Other")]

    @api.depends("date_from", "date_to", "location_scope", "cprojectid")
    def _compute_name(self):
        location_name_map = dict(self.get_location_scope_selection())
        for rec in self:
            name_parts = ["%s ~ %s" % (rec.date_from or "", rec.date_to or "")]
            if rec.location_scope:
                name_parts.append(location_name_map.get(rec.location_scope, rec.location_scope))
            if rec.cprojectid:
                name_parts.append(rec.cprojectid)
            rec.name = " / ".join(name_parts)

    def action_refresh_report(self):
        project_model = self.env["project.project"].sudo()
        location_model = self.env["stock.location"].sudo()
        report_line_model = self.env["sunrise.inbound.pallet.summary.report.line"]
        action = False
        sunrise_project = project_model.search([("name", "=", "SUNRISE")], limit=1)
        if not sunrise_project:
            raise ValidationError(_("SUNRISE project was not found."))
        for rec in self:
            if rec.date_from > rec.date_to:
                raise ValidationError(_("Date From must not be later than Date To."))
            filters = {
                "date_from": rec.date_from,
                "date_to": rec.date_to,
                "project_id": sunrise_project.id,
                "cprojectid": rec.cprojectid,
                "timezone": self.env.context.get("tz") or self.env.user.tz or "UTC",
            }
            configured_location_ids = set(sunrise_project.mapped("portal_stock_location_line_ids").ids) if "portal_stock_location_line_ids" in project_model._fields else set()
            if rec.location_scope == "other":
                configured_internal_location_ids = set(location_model.search([("id", "child_of", list(configured_location_ids)), ("usage", "=", "internal")]).ids) if configured_location_ids else set()
                all_internal_location_ids = set(location_model.search([("usage", "=", "internal")]).ids)
                filters["location_ids"] = list(all_internal_location_ids - configured_internal_location_ids)
            elif rec.location_scope:
                try:
                    location_id = int(rec.location_scope.removeprefix("location_"))
                except ValueError:
                    raise ValidationError(_("Location must be a valid record."))
                if location_id not in configured_location_ids:
                    raise ValidationError(_("Location must be configured on the SUNRISE project."))
                filters["location_id"] = location_id
            summary_data_list = self.env["stock.move.line"].get_inbound_pallet_summary(filters)
            rec.inbound_summary_lines.unlink()
            report_line_values = []
            for summary_data in summary_data_list:
                report_line_values.append({
                    "report_id": rec.id,
                    "first_inbound_date": summary_data["first_inbound_datetime"],
                    "inbound_order_id": summary_data["inbound_order_id"],
                    "cproject_ids": summary_data["cproject_ids"],
                    "opening_pallet_count": summary_data["opening_pallet_count"],
                    "inbound_pallet_count": summary_data["inbound_pallet_count"],
                    "outbound_pallet_count": summary_data["outbound_pallet_count"],
                    "closing_pallet_count": summary_data["closing_pallet_count"],
                    "closing_location_summary": summary_data["closing_location_summary"],
                    "remain_period_age_days": summary_data["remain_period_age_days"],
                    "remain_total_age_days": summary_data["remain_total_age_days"],
                    "outbound_lines": [(0, 0, {
                        "outbound_date": outbound_data["outbound_date"],
                        "pallet_count": outbound_data["pallet_count"],
                        "stock_days": outbound_data["stock_days"],
                    }) for outbound_data in summary_data["outbound_lines"]],
                })
            if report_line_values:
                report_line_model.create(report_line_values)
            rec.write({"state": "done", "refreshed_by_id": self.env.user.id, "refreshed_datetime": fields.Datetime.now()})
            action = {"type": "ir.actions.act_window", "name": _("Inbound Pallet Summary Report"), "res_model": "sunrise.inbound.pallet.summary.report", "view_mode": "form", "res_id": rec.id, "target": "current"}
        return action

    def action_export_excel(self):
        report_line_model = self.env["sunrise.inbound.pallet.summary.report.line"].sudo()
        attachment_model = self.env["ir.attachment"]
        action = False
        for rec in self:
            if rec.state != "done":
                raise ValidationError(_("Please refresh the report before exporting."))
            report_lines = report_line_model.search([("report_id", "=", rec.id)], order="first_inbound_date asc, id asc")
            max_outbound_count = max((len(line.outbound_lines) for line in report_lines), default=0)
            headers = ["First Inbound Date", "Inbound", "Contract No", "Opening Pallets"]
            for outbound_index in range(max_outbound_count):
                outbound_number = outbound_index + 1
                headers.extend(["Outbound %s - Outbound Date" % outbound_number, "Outbound %s - Pallet Count" % outbound_number, "Outbound %s - Stock Days" % outbound_number])
            headers.extend(["Closing Pallets", "Remaining Period Age Days", "Remaining Total Age Days"])
            rows = []
            for line in report_lines:
                first_inbound_date = fields.Datetime.context_timestamp(rec, line.first_inbound_date).strftime("%Y-%m-%d %H:%M:%S") if line.first_inbound_date else ""
                values = [first_inbound_date, line.inbound_order_id.display_name or "", line.cproject_ids or "", line.opening_pallet_count]
                outbound_lines = sorted(line.outbound_lines, key=lambda outbound_line: (outbound_line.outbound_date, outbound_line.id))
                for outbound_index in range(max_outbound_count):
                    outbound_line = outbound_lines[outbound_index] if outbound_index < len(outbound_lines) else False
                    values.extend([
                        fields.Date.to_string(outbound_line.outbound_date) if outbound_line else None,
                        outbound_line.pallet_count if outbound_line else None,
                        outbound_line.stock_days if outbound_line else None,
                    ])
                values.extend([line.closing_pallet_count, line.remain_period_age_days, line.remain_total_age_days])
                rows.append(values)
            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output, {"in_memory": True})
            worksheet = workbook.add_worksheet("Inbound Summary")
            title_format = workbook.add_format({"bold": True, "font_size": 14, "align": "center", "valign": "vcenter"})
            header_format = workbook.add_format({"bold": True, "align": "center", "valign": "vcenter", "text_wrap": True, "bg_color": "#D9EAF7", "border": 1})
            text_format = workbook.add_format({"border": 1, "valign": "vcenter", "text_wrap": True})
            number_format = workbook.add_format({"border": 1, "valign": "vcenter", "align": "right", "num_format": "0"})
            worksheet.merge_range(0, 0, 0, len(headers) - 1, "%s - %s" % (_("Inbound Pallet Summary"), rec.name or rec.id), title_format)
            worksheet.write_row(2, 0, headers, header_format)
            for row_index, values in enumerate(rows, start=3):
                for column_index, value in enumerate(values):
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        worksheet.write_number(row_index, column_index, value, number_format)
                    else:
                        worksheet.write(row_index, column_index, "" if value is None else value, text_format)
            worksheet.freeze_panes(3, 0)
            worksheet.autofilter(2, 0, max(2, len(rows) + 2), len(headers) - 1)
            worksheet.set_column(0, 0, 22)
            worksheet.set_column(1, 1, 24)
            worksheet.set_column(2, 2, 24)
            worksheet.set_column(3, len(headers) - 1, 16)
            workbook.close()
            output.seek(0)
            attachment = attachment_model.create({
                "name": "Inbound_Pallet_Summary_%s.xlsx" % (rec.id,),
                "type": "binary",
                "datas": base64.b64encode(output.read()),
                "res_model": rec._name,
                "res_id": rec.id,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            })
            action = {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % attachment.id, "target": "self"}
        return action


class SunriseInboundPalletSummaryReportLine(models.Model):
    _name = "sunrise.inbound.pallet.summary.report.line"
    _description = "Sunrise Inbound Pallet Summary Report Line"
    _order = "id desc"

    report_id = fields.Many2one("sunrise.inbound.pallet.summary.report", string="Report", required=True, readonly=True, ondelete="cascade", index=True, copy=False)
    first_inbound_date = fields.Datetime(string="First Inbound Date", required=True, readonly=True, index=True, copy=False)
    inbound_order_id = fields.Many2one("world.depot.inbound.order", string="Inbound", required=True, readonly=True, ondelete="restrict", index=True, copy=False)

    cproject_ids = fields.Char(string="Contract No", readonly=True, copy=False)
    opening_pallet_count = fields.Integer(string="Opening Pallets", readonly=True, copy=False)
    inbound_pallet_count = fields.Integer(string="Inbound Pallets", readonly=True, copy=False)
    outbound_pallet_count = fields.Integer(string="Outbound Pallets", readonly=True, copy=False)
    closing_pallet_count = fields.Integer(string="Closing Pallets", readonly=True, copy=False)
    closing_location_summary = fields.Char(string="Closing Location Summary", readonly=True, copy=False)
    remain_period_age_days = fields.Integer(string="Remaining Period Age Days", readonly=True, copy=False)
    remain_total_age_days = fields.Integer(string="Remaining Total Age Days", readonly=True, copy=False)
    outbound_lines = fields.One2many("sunrise.inbound.pallet.summary.outbound.line", "report_line_id", string="Outbound Details", readonly=True, copy=False)


class SunriseInboundPalletSummaryOutboundLine(models.Model):
    _name = "sunrise.inbound.pallet.summary.outbound.line"
    _description = "Sunrise Inbound Pallet Summary Outbound Line"
    _order = "id desc"

    report_line_id = fields.Many2one("sunrise.inbound.pallet.summary.report.line", string="Inbound Summary", required=True, readonly=True, ondelete="cascade", index=True, copy=False)
    outbound_date = fields.Date(string="Outbound Date", required=True, readonly=True, index=True, copy=False)
    pallet_count = fields.Integer(string="Pallet Count", required=True, readonly=True, copy=False)
    stock_days = fields.Integer(string="Stock Days", required=True, readonly=True, copy=False)
