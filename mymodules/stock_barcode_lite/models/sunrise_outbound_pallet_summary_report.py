# -*- coding: utf-8 -*-

import base64
import io
from collections import defaultdict
from datetime import datetime, time, timedelta

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def format_product_template_name(product_template):
    if not product_template:
        return ""
    standard_product = product_template.product_variant_ids.filtered(lambda product: "Standard Packaging" in product.product_template_attribute_value_ids.mapped("name"))[:1]
    product_code = standard_product.barcode or standard_product.default_code or product_template.barcode or product_template.default_code or ""
    product_name = product_template.name or ""
    return "[%s] %s" % (product_code, product_name) if product_code and product_name else product_code or product_name


class SunriseOutboundPalletSummaryReport(models.Model):
    _name = "sunrise.outbound.pallet.summary.report"
    _description = "Sunrise Outbound Pallet Summary Report"
    _order = "id desc"

    name = fields.Char(string="Name", compute="_compute_name", store=True, readonly=True, copy=False, index=True)
    date_from = fields.Date(string="Date From", required=True, default=lambda self: fields.Date.context_today(self).replace(day=1), index=True)
    date_to = fields.Date(string="Date To", required=True, default=fields.Date.context_today, index=True)
    location_scope = fields.Selection(selection="get_location_scope_selection", string="Location", copy=False, index=True)
    cprojectid = fields.Char(string="Outbound Sunrise Ref", copy=False, index=True)
    state = fields.Selection([("draft", "Draft"), ("done", "Done")], string="State", default="draft", required=True, readonly=True, copy=False, index=True)
    refreshed_by_id = fields.Many2one("res.users", string="Last Refreshed By", readonly=True, copy=False)
    refreshed_datetime = fields.Datetime(string="Last Refreshed At", readonly=True, copy=False, index=True)
    line_ids = fields.One2many("sunrise.outbound.pallet.summary.report.line", "report_id", string="Outbound Summary Lines", readonly=True, copy=False)

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
        move_line_model = self.env["stock.move.line"].sudo()
        outbound_product_model = self.env["world.depot.outbound.order.product"].sudo()
        project_model = self.env["project.project"].sudo()
        location_model = self.env["stock.location"].sudo()
        report_line_model = self.env["sunrise.outbound.pallet.summary.report.line"]
        pallet_line_model = self.env["sunrise.outbound.pallet.summary.report.pallet.line"]
        action = False
        use_sunrise_business_date = False

        def get_business_datetime(move_line):
            if not use_sunrise_business_date:
                return move_line.date
            picking = move_line.picking_id
            outbound_product = outbound_product_model.browse(move_line.move_id.outbound_order_product_id)
            outbound_order = picking.outbound_order_id or outbound_product.outbound_order_id
            business_date = picking.inbound_order_id.actual_inbound_date if picking.inbound_order_id else outbound_order.o_date if outbound_order else False
            return datetime.combine(business_date, time.min) if business_date else False

        for rec in self:
            if rec.state == "done":
                raise ValidationError(_("A refreshed report cannot be refreshed again."))
            if rec.date_from > rec.date_to:
                raise ValidationError(_("Date From must not be later than Date To."))

            sunrise_project = project_model.search([("name", "=", "SUNRISE")], limit=1)
            if not sunrise_project:
                raise ValidationError(_("SUNRISE project was not found."))
            use_sunrise_business_date = sunrise_project.stock_report_date_mode == "business"
            configured_location_ids = set(sunrise_project.mapped("portal_stock_location_line_ids").ids) if "portal_stock_location_line_ids" in project_model._fields else set()
            location_ids = set()
            if rec.location_scope == "other":
                configured_internal_location_ids = set(location_model.search([("id", "child_of", list(configured_location_ids)), ("usage", "=", "internal")]).ids) if configured_location_ids else set()
                all_internal_location_ids = set(location_model.search([("usage", "=", "internal")]).ids)
                location_ids = all_internal_location_ids - configured_internal_location_ids
            elif rec.location_scope:
                try:
                    location_id = int(rec.location_scope.removeprefix("location_"))
                except ValueError:
                    raise ValidationError(_("Location must be a valid record."))
                if location_id not in configured_location_ids:
                    raise ValidationError(_("Location must be configured on the SUNRISE project."))
                location_ids = set(location_model.search([("id", "child_of", location_id)]).ids)

            date_to_exclusive = datetime.combine(rec.date_to + timedelta(days=1), time.min)
            missing_outbound_move_lines = move_line_model.search([
                ("state", "=", "done"),
                ("date", "<", date_to_exclusive),
                ("picking_id.state", "=", "done"),
                ("picking_id.picking_type_id.code", "=", "outgoing"),
                ("picking_id.outbound_order_id.project", "=", sunrise_project.id),
                ("picking_id.outbound_order_id.o_date", "=", False),
                ("location_id.usage", "=", "internal"),
                ("location_dest_id.usage", "!=", "internal"),
            ], order="date asc, id asc") if use_sunrise_business_date else move_line_model.browse()
            cprojectid_keyword = (rec.cprojectid or "").strip().lower()
            for move_line in missing_outbound_move_lines:
                outbound_product = outbound_product_model.browse(move_line.move_id.outbound_order_product_id)
                if cprojectid_keyword and cprojectid_keyword not in (outbound_product.cprojectid or "").lower():
                    continue
                raise ValidationError(_("Outbound Date is required for SUNRISE outbound order %s.") % move_line.picking_id.outbound_order_id.display_name)
            outbound_move_line_domain = [
                ("state", "=", "done"),
                ("picking_id.state", "=", "done"),
                ("picking_id.picking_type_id.code", "=", "outgoing"),
                ("picking_id.outbound_order_id.project", "=", sunrise_project.id),
                ("location_id.usage", "=", "internal"),
                ("location_dest_id.usage", "!=", "internal"),
            ]
            if use_sunrise_business_date:
                outbound_move_line_domain.extend([("picking_id.outbound_order_id.o_date", ">=", rec.date_from), ("picking_id.outbound_order_id.o_date", "<=", rec.date_to)])
            else:
                outbound_move_line_domain.extend([("date", ">=", datetime.combine(rec.date_from, time.min)), ("date", "<", date_to_exclusive)])
            outbound_move_lines = move_line_model.search(outbound_move_line_domain, order="date asc, id asc")
            order_data_map = {}
            for move_line in outbound_move_lines:
                if rec.location_scope and move_line.location_id.id not in location_ids:
                    continue
                picking = move_line.picking_id
                outbound_order = picking.outbound_order_id
                outbound_product = outbound_product_model.browse(move_line.move_id.outbound_order_product_id)
                cprojectid = (outbound_product.cprojectid or "").strip()
                outbound_order_product_lines = outbound_order.outbound_order_product_ids
                order_data = order_data_map.setdefault(outbound_order.id, {
                    "outbound_order": outbound_order,
                    "outbound_datetime": datetime.combine(outbound_order.o_date, time.min) if use_sunrise_business_date else move_line.date,
                    "cprojectid_set": set(),
                    "product_name_set": {format_product_template_name(line.product_id.product_tmpl_id) for line in outbound_order_product_lines if line.product_id and line.product_id.product_tmpl_id},
                    "product_quantity_total": sum(line.quantity or 0.0 for line in outbound_order_product_lines),
                    "pallet_data_map": {},
                })
                if not use_sunrise_business_date:
                    order_data["outbound_datetime"] = max(order_data["outbound_datetime"], move_line.date)
                if cprojectid:
                    order_data["cprojectid_set"].add(cprojectid)
                product_name = format_product_template_name(move_line.product_id.product_tmpl_id)
                if not move_line.package_id:
                    continue
                pallet_data = order_data["pallet_data_map"].setdefault(move_line.package_id.id, {
                    "package": move_line.package_id,
                    "cprojectid_set": set(),
                    "product_name_set": set(),
                    "outbound_quantity": 0.0,
                    "source_location_name_set": set(),
                })
                if cprojectid:
                    pallet_data["cprojectid_set"].add(cprojectid)
                pallet_data["product_name_set"].add(product_name)
                pallet_data["outbound_quantity"] += move_line.quantity
                source_location_name = move_line.location_id.complete_name or move_line.location_id.display_name
                if source_location_name:
                    pallet_data["source_location_name_set"].add(source_location_name)

            if cprojectid_keyword:
                order_data_map = {
                    outbound_order_id: order_data
                    for outbound_order_id, order_data in order_data_map.items()
                    if any(cprojectid_keyword in cprojectid.lower() for cprojectid in order_data["cprojectid_set"])
                }

            package_ids = sorted({
                package_id
                for order_data in order_data_map.values()
                for package_id in order_data["pallet_data_map"]
            })
            package_inbound_data_map = {}
            if package_ids:
                inbound_move_line_domain = [
                    ("state", "=", "done"),
                    ("picking_id.state", "=", "done"),
                    ("picking_id.picking_type_id.code", "=", "incoming"),
                    ("result_package_id", "in", package_ids),
                    ("location_id.usage", "!=", "internal"),
                    ("location_dest_id.usage", "=", "internal"),
                ]
                inbound_move_line_domain.append(("picking_id.inbound_order_id.actual_inbound_date", "<=", rec.date_to) if use_sunrise_business_date else ("date", "<", date_to_exclusive))
                inbound_move_lines = move_line_model.search(inbound_move_line_domain, order="date asc, id asc")
                for move_line in inbound_move_lines:
                    package_id = move_line.result_package_id.id
                    inbound_datetime = datetime.combine(move_line.picking_id.inbound_order_id.actual_inbound_date, time.min) if use_sunrise_business_date else move_line.date
                    inbound_data = package_inbound_data_map.setdefault(package_id, {
                        "inbound_datetime": inbound_datetime,
                        "inbound_picking_id": move_line.picking_id.id,
                        "inbound_quantity_total": 0.0,
                    })
                    if inbound_datetime < inbound_data["inbound_datetime"]:
                        inbound_data["inbound_datetime"] = inbound_datetime
                        inbound_data["inbound_picking_id"] = move_line.picking_id.id
                        inbound_data["inbound_quantity_total"] = 0.0
                    if move_line.picking_id.id == inbound_data["inbound_picking_id"]:
                        inbound_data["inbound_quantity_total"] += move_line.quantity

            package_consumed_datetime_map = {}
            if package_ids:
                package_move_lines = move_line_model.search([
                    ("state", "=", "done"),
                    "|",
                    ("package_id", "in", package_ids),
                    ("result_package_id", "in", package_ids),
                ], order="date asc, id asc")
                package_quantity_map = defaultdict(lambda: defaultdict(float))
                package_event_data_list = []
                for move_line in package_move_lines:
                    event_datetime = move_line.date
                    is_actual_inbound = move_line.location_id.usage != "internal" and move_line.location_dest_id.usage == "internal"
                    is_actual_outbound = move_line.location_id.usage == "internal" and move_line.location_dest_id.usage != "internal"
                    if use_sunrise_business_date and (is_actual_inbound or is_actual_outbound):
                        event_datetime = get_business_datetime(move_line)
                        if not event_datetime:
                            if move_line.date < date_to_exclusive:
                                inbound_order = move_line.picking_id.inbound_order_id
                                outbound_product = outbound_product_model.browse(move_line.move_id.outbound_order_product_id)
                                outbound_order = move_line.picking_id.outbound_order_id or outbound_product.outbound_order_id
                                field_name = _("Manual Inbound Date") if inbound_order else _("Outbound Date")
                                order_name = inbound_order.display_name if inbound_order else outbound_order.display_name
                                raise ValidationError(_("%(field_name)s is required for SUNRISE order %(order_name)s.") % {"field_name": field_name, "order_name": order_name})
                            continue
                    if event_datetime >= date_to_exclusive:
                        continue
                    package_event_data_list.append((event_datetime, move_line))
                for event_datetime, move_line in sorted(package_event_data_list, key=lambda event_data: (event_data[0], event_data[1].date, event_data[1].id)):
                    source_package_id = move_line.package_id.id
                    destination_package_id = move_line.result_package_id.id or source_package_id
                    package_delta_map = defaultdict(float)
                    if move_line.location_id.usage == "internal" and source_package_id in package_ids:
                        package_delta_map[source_package_id] -= move_line.quantity
                    if move_line.location_dest_id.usage == "internal" and destination_package_id in package_ids:
                        package_delta_map[destination_package_id] += move_line.quantity
                    for package_id, quantity_delta in package_delta_map.items():
                        before_active = any(quantity > 0.000001 for quantity in package_quantity_map[package_id].values())
                        package_quantity_map[package_id][(move_line.product_id.id, move_line.lot_id.id)] += quantity_delta
                        after_active = any(quantity > 0.000001 for quantity in package_quantity_map[package_id].values())
                        if not before_active and after_active:
                            package_consumed_datetime_map[package_id] = False
                        elif before_active and not after_active:
                            package_consumed_datetime_map[package_id] = event_datetime

            rec.line_ids.unlink()
            report_line_values = []
            for order_data in order_data_map.values():
                outbound_order = order_data["outbound_order"]
                report_line_values.append({
                    "report_id": rec.id,
                    "outbound_order_id": outbound_order.id,
                    "order_date": outbound_order.date,
                    "sunrise_ref": ", ".join(sorted(order_data["cprojectid_set"])),
                    "outbound_datetime": order_data["outbound_datetime"],
                    "system_document_no": outbound_order.billno,
                    "outbound_pallet_count": len(outbound_order.outbound_order_product_ids.mapped("package_id")),
                    "completed_outbound_pallet_count": sum(1 for package_id in order_data["pallet_data_map"] if package_consumed_datetime_map.get(package_id)),
                    "product_names": ", ".join(sorted(order_data["product_name_set"])),
                    "product_quantity_summary": order_data["product_quantity_total"],
                })
            report_lines = report_line_model.create(report_line_values) if report_line_values else report_line_model
            report_line_map = {report_line.outbound_order_id.id: report_line for report_line in report_lines}
            pallet_line_values = []
            for outbound_order_id, order_data in order_data_map.items():
                report_line = report_line_map[outbound_order_id]
                for package_id, pallet_data in order_data["pallet_data_map"].items():
                    inbound_data = package_inbound_data_map.get(package_id, {})
                    pallet_line_values.append({
                        "report_line_id": report_line.id,
                        "package_id": package_id,
                        "sunrise_ref": ", ".join(sorted(pallet_data["cprojectid_set"])),
                        "product_names": ", ".join(sorted(pallet_data["product_name_set"])),
                        "inbound_quantity_summary": inbound_data.get("inbound_quantity_total", 0.0),
                        "outbound_quantity": pallet_data["outbound_quantity"],
                        "inbound_datetime": inbound_data.get("inbound_datetime"),
                        "consumed_datetime": package_consumed_datetime_map.get(package_id),
                        "location_summary": ", ".join(sorted(pallet_data["source_location_name_set"])),
                    })
            if pallet_line_values:
                pallet_line_model.create(pallet_line_values)
            rec.write({"state": "done", "refreshed_by_id": self.env.user.id, "refreshed_datetime": fields.Datetime.now()})
            action = {"type": "ir.actions.act_window", "name": _("Outbound Pallet Summary Report"), "res_model": "sunrise.outbound.pallet.summary.report", "view_mode": "form", "res_id": rec.id, "target": "current"}
        return action

    def action_export_excel(self):
        report_line_model = self.env["sunrise.outbound.pallet.summary.report.line"].sudo()
        attachment_model = self.env["ir.attachment"]
        action = False
        for rec in self:
            if rec.state != "done":
                raise ValidationError(_("Please refresh the report before exporting."))
            report_lines = report_line_model.search([("report_id", "=", rec.id)], order="order_date asc, id asc")
            headers = ["Outbound Order Date", "Outbound Sunrise Ref", "Outbound Date", "Outbound No", "Total Outbound Pallets", "Completed Outbound Pallets", "Outbound Products", "Pallet Outbound Product Quantity", "Pallet No", "Inbound Date", "Fully Outbound Date", "Pallet Inbound Product Quantity"]
            rows = []
            for line in report_lines:
                outbound_order = line.outbound_order_id
                outbound_datetime = fields.Date.to_string(line.outbound_datetime.date()) if line.outbound_datetime else ""
                for pallet_line in line.pallet_line_ids.sorted(key=lambda item: (item.package_id.display_name or item.package_id.name or "", item.id)):
                    rows.append([
                        fields.Date.to_string(outbound_order.date or line.order_date) if outbound_order.date or line.order_date else "",
                        pallet_line.sunrise_ref or line.sunrise_ref or "",
                        outbound_datetime,
                        line.system_document_no or outbound_order.billno or "",
                        line.outbound_pallet_count or 0,
                        line.completed_outbound_pallet_count or 0,
                        line.product_names or pallet_line.product_names or "",
                        pallet_line.outbound_quantity or 0.0,
                        pallet_line.package_id.display_name or pallet_line.package_id.name or "",
                        fields.Date.to_string(pallet_line.inbound_datetime.date()) if pallet_line.inbound_datetime else "",
                        fields.Date.to_string(pallet_line.consumed_datetime.date()) if pallet_line.consumed_datetime else "",
                        pallet_line.inbound_quantity_summary or 0.0,
                    ])
            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output, {"in_memory": True})
            worksheet = workbook.add_worksheet("Outbound Summary")
            title_format = workbook.add_format({"bold": True, "font_size": 14, "align": "center", "valign": "vcenter"})
            header_format = workbook.add_format({"bold": True, "align": "center", "valign": "vcenter", "text_wrap": True, "bg_color": "#D9EAF7", "border": 1})
            text_format = workbook.add_format({"border": 1, "valign": "vcenter", "text_wrap": True})
            number_format = workbook.add_format({"border": 1, "valign": "vcenter", "align": "right", "num_format": "0.00"})
            worksheet.merge_range(0, 0, 0, len(headers) - 1, "%s - %s" % (_("Outbound Pallet Summary"), rec.name or rec.id), title_format)
            for column_index, header in enumerate(headers):
                worksheet.write(2, column_index, header, header_format)
            for row_index, values in enumerate(rows, start=3):
                for column_index, value in enumerate(values):
                    worksheet.write_number(row_index, column_index, value, number_format) if isinstance(value, (int, float)) and not isinstance(value, bool) else worksheet.write(row_index, column_index, value, text_format)
            worksheet.freeze_panes(3, 0)
            worksheet.autofilter(2, 0, max(2, len(rows) + 2), len(headers) - 1)
            worksheet.set_column(0, 0, 20)
            worksheet.set_column(1, 2, 24)
            worksheet.set_column(3, 3, 18)
            worksheet.set_column(4, 5, 12)
            worksheet.set_column(6, 6, 32)
            worksheet.set_column(7, 8, 18)
            worksheet.set_column(9, 10, 20)
            worksheet.set_column(11, 11, 18)
            workbook.close()
            output.seek(0)
            report_name = (rec.name or "Outbound_Pallet_Summary").replace("/", "_").replace("\\", "_").replace(":", "_")
            attachment = attachment_model.create({
                "name": "Outbound_Pallet_Summary_%s_%s.xlsx" % (report_name, rec.id),
                "type": "binary",
                "datas": base64.b64encode(output.read()),
                "res_model": rec._name,
                "res_id": rec.id,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            })
            action = {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % attachment.id, "target": "self"}
        return action


class SunriseOutboundPalletSummaryReportLine(models.Model):
    _name = "sunrise.outbound.pallet.summary.report.line"
    _description = "Sunrise Outbound Pallet Summary Report Line"
    _order = "id desc"

    report_id = fields.Many2one("sunrise.outbound.pallet.summary.report", string="Report", required=True, readonly=True, ondelete="cascade", index=True, copy=False)
    outbound_order_id = fields.Many2one("world.depot.outbound.order", string="Outbound Order", required=True, readonly=True, ondelete="restrict", index=True, copy=False)
    order_date = fields.Date(string="Order Date", readonly=True, index=True, copy=False)
    sunrise_ref = fields.Char(string="Outbound Sunrise Ref", readonly=True, copy=False)
    outbound_datetime = fields.Datetime(string="Outbound Datetime", required=True, readonly=True, index=True, copy=False)
    system_document_no = fields.Char(string="Outbound No", readonly=True, copy=False)
    outbound_pallet_count = fields.Integer(string="Total Outbound Pallets", readonly=True, copy=False)
    completed_outbound_pallet_count = fields.Integer(string="Completed Outbound Pallets", readonly=True, copy=False)
    product_names = fields.Char(string="Outbound Products", readonly=True, copy=False)
    product_quantity_summary = fields.Float(string="Outbound Total product Quantity", readonly=True, copy=False)
    pallet_line_ids = fields.One2many("sunrise.outbound.pallet.summary.report.pallet.line", "report_line_id", string="Pallet Lines", readonly=True, copy=False)


class SunriseOutboundPalletSummaryReportPalletLine(models.Model):
    _name = "sunrise.outbound.pallet.summary.report.pallet.line"
    _description = "Sunrise Outbound Pallet Summary Report Pallet Line"
    _order = "id desc"

    report_line_id = fields.Many2one("sunrise.outbound.pallet.summary.report.line", string="Outbound Summary", required=True, readonly=True, ondelete="cascade", index=True, copy=False)
    package_id = fields.Many2one("stock.quant.package", string="Pallet No", required=True, readonly=True, ondelete="restrict", index=True, copy=False)
    sunrise_ref = fields.Char(string="Outbound Sunrise Ref", readonly=True, copy=False)
    product_names = fields.Char(string="Products", readonly=True, copy=False)
    inbound_quantity_summary = fields.Float(string="Inbound Product Quantity", readonly=True, copy=False)
    outbound_quantity = fields.Float(string="Outbound Product Quantity", readonly=True, copy=False)
    inbound_datetime = fields.Datetime(string="Inbound Datetime", readonly=True, index=True, copy=False)
    consumed_datetime = fields.Datetime(string="Fully Outbound Datetime", readonly=True, index=True, copy=False)
    location_summary = fields.Char(string="Outbound Location", readonly=True, copy=False)
