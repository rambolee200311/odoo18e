# -*- coding: utf-8 -*-

import base64
import io
from collections import defaultdict

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SunriseLocationOccupancyReport(models.Model):
    _name = "sunrise.location.occupancy.report"
    _description = "Sunrise Location Occupancy Report"
    _order = "id desc"

    name = fields.Char(string="Name", compute="_compute_name", store=True, readonly=True, copy=False, index=True)
    warehouse_ids = fields.Many2many("stock.warehouse", string="Warehouses", required=True, copy=False)
    parent_location_id = fields.Many2one("stock.location", string="Location Parent", required=True, copy=False, index=True)
    project_id = fields.Many2one("project.project", string="Project", copy=False, index=True)
    location_state = fields.Selection([("all", "All"), ("occupied", "Occupied"), ("empty", "Empty")], string="Location State", default="all", required=True, copy=False, index=True)
    package_name = fields.Char(string="Package No", copy=False, index=True)
    lot_name = fields.Char(string="Lot No", copy=False, index=True)
    state = fields.Selection([("draft", "Draft"), ("done", "Done")], string="State", default="draft", required=True, readonly=True, copy=False, index=True)
    refreshed_by_id = fields.Many2one("res.users", string="Last Refreshed By", readonly=True, copy=False)
    refreshed_datetime = fields.Datetime(string="Last Refreshed At", readonly=True, copy=False, index=True)
    line_ids = fields.One2many("sunrise.location.occupancy.report.line", "report_id", string="Location Occupancy Lines", readonly=True, copy=False)

    @api.depends("refreshed_datetime")
    def _compute_name(self):
        for rec in self:
            if rec.refreshed_datetime:
                rec.name = _("Warehouse Location Occupancy - %s") % fields.Datetime.context_timestamp(rec, rec.refreshed_datetime).strftime("%Y-%m-%d %H:%M:%S")
            else:
                rec.name = _("Warehouse Location Occupancy")

    def action_refresh_current_report(self):
        env = self.env
        location_model = env["stock.location"].sudo()
        quant_model = env["stock.quant"].sudo()
        move_line_model = env["stock.move.line"].sudo()
        report_line_model = env["sunrise.location.occupancy.report.line"]
        action = False

        for rec in self:
            if not rec.warehouse_ids:
                raise ValidationError(_("Please select at least one warehouse."))
            if not rec.parent_location_id:
                raise ValidationError(_("Please select a location parent."))
            if rec.parent_location_id.usage not in ("view", "internal"):
                raise ValidationError(_("The location parent must be a view or internal location."))
            parent_location = location_model.search([
                ("id", "=", rec.parent_location_id.id),
                ("id", "child_of", rec.warehouse_ids.mapped("view_location_id").ids),
            ], limit=1)
            if not parent_location:
                raise ValidationError(_("The location parent must belong to the selected warehouses."))

            location_ids = location_model.search([
                ("id", "child_of", rec.parent_location_id.id),
                ("usage", "=", "internal"),
                ("active", "=", True),
                ("warehouse_id", "in", rec.warehouse_ids.ids),
            ], order="warehouse_id asc, complete_name asc, id asc")
            all_quants = quant_model.search([
                ("location_id", "in", location_ids.ids),
                ("quantity", ">", 0),
            ], order="location_id asc, package_id asc, lot_id asc, product_id asc, id asc")
            physical_occupied_location_ids = set(all_quants.mapped("location_id").ids)
            package_ids = set(all_quants.mapped("package_id").ids)
            lifecycle_start_map = {}
            lifecycle_project_map = {}
            if package_ids:
                move_lines = move_line_model.search([
                    ("move_id.state", "=", "done"),
                    "|",
                    ("package_id", "in", list(package_ids)),
                    ("result_package_id", "in", list(package_ids)),
                ], order="date asc, id asc")
                package_quantity_map = defaultdict(lambda: defaultdict(float))
                for move_line in move_lines:
                    source_usage = move_line.location_id.usage
                    destination_usage = move_line.location_dest_id.usage
                    package = False
                    signed_quantity = 0.0
                    if source_usage == "inventory" and destination_usage == "internal":
                        package = move_line.result_package_id or move_line.package_id
                        signed_quantity = move_line.quantity
                    elif source_usage == "internal" and destination_usage == "inventory":
                        package = move_line.package_id or move_line.result_package_id
                        signed_quantity = -move_line.quantity
                    elif source_usage != "internal" and destination_usage == "internal":
                        package = move_line.result_package_id or move_line.package_id
                        signed_quantity = move_line.quantity
                    elif source_usage == "internal" and destination_usage != "internal":
                        package = move_line.package_id or move_line.result_package_id
                        signed_quantity = -move_line.quantity
                    if not package or package.id not in package_ids or not signed_quantity:
                        continue

                    product_lot_quantity_map = package_quantity_map[package.id]
                    before_active = any(quantity > 0.000001 for quantity in product_lot_quantity_map.values())
                    product_lot_quantity_map[(move_line.product_id.id, move_line.lot_id.id)] += signed_quantity
                    after_active = any(quantity > 0.000001 for quantity in product_lot_quantity_map.values())
                    if not before_active and after_active:
                        lifecycle_start_map[package.id] = move_line.date
                        lifecycle_project_map[package.id] = move_line.picking_id.project_id.id

            package_keyword = (rec.package_name or "").strip().lower()
            lot_keyword = (rec.lot_name or "").strip().lower()
            visible_quants = all_quants.filtered(
                lambda quant: (
                    (
                        not rec.project_id
                        or (
                            quant.package_id
                            and lifecycle_project_map.get(quant.package_id.id) == rec.project_id.id
                        )
                    )
                    and (
                        not package_keyword
                        or package_keyword in (quant.package_id.name or "").lower()
                        or package_keyword in (quant.package_id.barcode or "").lower()
                    )
                    and (not lot_keyword or lot_keyword in (quant.lot_id.name or "").lower())
                )
            )

            group_data_map = {}
            template_ids_by_package_lot = defaultdict(set)
            uom_ids_by_product_lot = defaultdict(set)
            for quant in visible_quants:
                product_template = quant.product_id.product_tmpl_id
                package = quant.package_id
                lot = quant.lot_id
                owner = quant.owner_id
                uom = quant.product_id.uom_id
                group_key = (quant.location_id.id, package.id, lot.id, product_template.id, owner.id, uom.id)
                group_data = group_data_map.setdefault(group_key, {
                    "warehouse": quant.location_id.warehouse_id,
                    "location": quant.location_id,
                    "package": package,
                    "lot": lot,
                    "product_template": product_template,
                    "owner": owner,
                    "uom": uom,
                    "quantity": 0.0,
                })
                group_data["quantity"] += quant.quantity
                if package:
                    template_ids_by_package_lot[(quant.location_id.id, package.id, lot.id)].add(product_template.id)
                    uom_ids_by_product_lot[(quant.location_id.id, package.id, lot.id, product_template.id, owner.id)].add(uom.id)

            line_values_list = []
            if rec.location_state in ("all", "occupied"):
                for group_key, group_data in group_data_map.items():
                    location_id, package_id, lot_id, product_template_id, owner_id, uom_id = group_key
                    anomaly_messages = []
                    if not package_id:
                        anomaly_messages.append(_("Missing Package"))
                    if not lot_id:
                        anomaly_messages.append(_("Missing Lot"))
                    if package_id and len(template_ids_by_package_lot[(location_id, package_id, lot_id)]) > 1:
                        anomaly_messages.append(_("Mixed Product Templates"))
                    if package_id and len(uom_ids_by_product_lot[(location_id, package_id, lot_id, product_template_id, owner_id)]) > 1:
                        anomaly_messages.append(_("Mixed UOM"))
                    if package_id and not lifecycle_start_map.get(package_id):
                        anomaly_messages.append(_("Missing Lifecycle Start"))
                    line_values_list.append({
                        "report_id": rec.id,
                        "warehouse_id": group_data["warehouse"].id,
                        "warehouse_code": group_data["warehouse"].code or "",
                        "location_id": group_data["location"].id,
                        "location_code": group_data["location"].complete_name or "",
                        "occupancy_state": "occupied",
                        "package_id": package_id,
                        "package_name": group_data["package"].name or group_data["package"].barcode or "",
                        "product_template_id": product_template_id,
                        "lot_id": lot_id,
                        "lot_name": group_data["lot"].name or "",
                        "expiration_datetime": group_data["lot"].expiration_date if lot_id else False,
                        "quantity": group_data["quantity"],
                        "uom_id": uom_id,
                        "first_inbound_datetime": lifecycle_start_map.get(package_id),
                        "project_id": lifecycle_project_map.get(package_id),
                        "owner_id": owner_id,
                        "anomaly_message": "; ".join(anomaly_messages),
                    })

            if rec.location_state in ("all", "empty"):
                for location in location_ids:
                    if location.id in physical_occupied_location_ids:
                        continue
                    line_values_list.append({
                        "report_id": rec.id,
                        "warehouse_id": location.warehouse_id.id,
                        "warehouse_code": location.warehouse_id.code or "",
                        "location_id": location.id,
                        "location_code": location.complete_name or "",
                        "occupancy_state": "empty",
                        "quantity": 0.0,
                    })

            rec.line_ids.unlink()
            if line_values_list:
                report_line_model.create(line_values_list)
            rec.write({
                "state": "done",
                "refreshed_by_id": env.user.id,
                "refreshed_datetime": fields.Datetime.now(),
            })
            action = {
                "type": "ir.actions.act_window",
                "res_model": rec._name,
                "res_id": rec.id,
                "view_mode": "form",
                "views": [(False, "form")],
                "target": "current",
            }
        return action

    def action_view_report_lines(self):
        action = False

        for rec in self:
            action = {
                "type": "ir.actions.act_window",
                "name": _("Warehouse Location Occupancy Lines"),
                "res_model": "sunrise.location.occupancy.report.line",
                "view_mode": "list",
                "domain": [("report_id", "=", rec.id)],
                "context": {"create": False, "edit": False},
                "target": "current",
            }
        return action

    def action_export_location_occupancy_excel(self):
        env = self.env
        report_line_model = env["sunrise.location.occupancy.report.line"].sudo()
        attachment_model = env["ir.attachment"]
        action = False

        for rec in self:
            if rec.state != "done":
                raise ValidationError(_("Please refresh the report before exporting."))

            report_lines = report_line_model.search([
                ("report_id", "=", rec.id),
            ], order="warehouse_code asc, location_code asc, package_name asc, lot_name asc, id asc")
            headers = ["Warehouse", "Location", "State", "Package", "Product", "Lot", "Expiration Date", "Quantity", "Unit", "First Inbound Time", "Project", "Owner", "Anomaly"]
            widths = [16, 28, 12, 22, 30, 20, 18, 14, 12, 22, 26, 26, 30]
            state_label_map = dict(report_line_model._fields["occupancy_state"].selection)
            rows = [
                [
                    line.warehouse_id.display_name or "",
                    line.location_code or "",
                    state_label_map.get(line.occupancy_state, ""),
                    line.package_name or "",
                    line.product_template_id.display_name or "",
                    line.lot_name or "",
                    fields.Datetime.context_timestamp(rec, line.expiration_datetime).strftime("%Y-%m-%d") if line.expiration_datetime else "",
                    line.quantity,
                    line.uom_id.name or "",
                    fields.Datetime.context_timestamp(rec, line.first_inbound_datetime).strftime("%Y-%m-%d %H:%M:%S") if line.first_inbound_datetime else "",
                    line.project_id.display_name or "",
                    line.owner_id.display_name or "",
                    line.anomaly_message or "",
                ]
                for line in report_lines
            ]
            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output, {"in_memory": True})
            worksheet = workbook.add_worksheet("Location Occupancy")
            title_format = workbook.add_format({"bold": True, "font_size": 14, "align": "center", "valign": "vcenter"})
            label_format = workbook.add_format({"bold": True, "border": 1})
            value_format = workbook.add_format({"border": 1})
            header_format = workbook.add_format({"bold": True, "align": "center", "valign": "vcenter", "text_wrap": True, "bg_color": "#D9EAF7", "border": 1})
            text_format = workbook.add_format({"border": 1, "valign": "vcenter", "text_wrap": True})
            number_format = workbook.add_format({"border": 1, "valign": "vcenter", "align": "right", "num_format": "0.00"})
            header_row = 6

            worksheet.merge_range(0, 0, 0, len(headers) - 1, "%s - %s" % (_("Warehouse Location Occupancy"), rec.name or rec.id), title_format)
            worksheet.write(2, 0, _("Warehouses"), label_format)
            worksheet.merge_range(2, 1, 2, 4, ", ".join(rec.warehouse_ids.mapped("display_name")), value_format)
            worksheet.write(3, 0, _("Refreshed At"), label_format)
            worksheet.merge_range(3, 1, 3, 4, fields.Datetime.context_timestamp(rec, rec.refreshed_datetime).strftime("%Y-%m-%d %H:%M:%S") if rec.refreshed_datetime else "", value_format)
            worksheet.write(4, 0, _("Project"), label_format)
            worksheet.merge_range(4, 1, 4, 4, rec.project_id.display_name or "", value_format)
            worksheet.write(5, 0, _("Location Parent"), label_format)
            worksheet.merge_range(5, 1, 5, 4, rec.parent_location_id.complete_name or "", value_format)
            worksheet.write_row(header_row, 0, headers, header_format)
            worksheet.freeze_panes(header_row + 1, 0)
            worksheet.autofilter(header_row, 0, header_row + len(rows), len(headers) - 1)
            for column, width in enumerate(widths):
                worksheet.set_column(column, column, width)
            for row, values in enumerate(rows, start=header_row + 1):
                for column, value in enumerate(values):
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        worksheet.write_number(row, column, value, number_format)
                    else:
                        worksheet.write(row, column, value or "", text_format)
            workbook.close()
            output.seek(0)
            attachment = attachment_model.create({
                "name": "Warehouse_Location_Occupancy_%s.xlsx" % (rec.id,),
                "type": "binary",
                "datas": base64.b64encode(output.read()),
                "res_model": rec._name,
                "res_id": rec.id,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            })
            action = {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % attachment.id, "target": "self"}
        return action


class SunriseLocationOccupancyReportLine(models.Model):
    _name = "sunrise.location.occupancy.report.line"
    _description = "Sunrise Location Occupancy Report Line"
    _order = "warehouse_code asc, location_code asc, package_name asc, lot_name asc, id asc"

    report_id = fields.Many2one("sunrise.location.occupancy.report", string="Report", required=True, ondelete="cascade", index=True, copy=False)
    warehouse_id = fields.Many2one("stock.warehouse", string="Warehouse", readonly=True, index=True, copy=False)
    warehouse_code = fields.Char(string="Warehouse Code", readonly=True, index=True, copy=False)
    location_id = fields.Many2one("stock.location", string="Location", readonly=True, index=True, copy=False)
    location_code = fields.Char(string="Location Code", readonly=True, index=True, copy=False)
    occupancy_state = fields.Selection([("occupied", "Occupied"), ("empty", "Empty")], string="State", required=True, readonly=True, index=True, copy=False)
    package_id = fields.Many2one("stock.quant.package", string="Package", readonly=True, index=True, copy=False)
    package_name = fields.Char(string="Package No", readonly=True, index=True, copy=False)
    product_template_id = fields.Many2one("product.template", string="Product", readonly=True, index=True, copy=False)
    lot_id = fields.Many2one("stock.lot", string="Lot", readonly=True, index=True, copy=False)
    lot_name = fields.Char(string="Lot No", readonly=True, index=True, copy=False)
    expiration_datetime = fields.Datetime(string="Expiration Date", readonly=True, copy=False, index=True)
    quantity = fields.Float(string="Quantity", readonly=True, copy=False)
    uom_id = fields.Many2one("uom.uom", string="Unit", readonly=True, copy=False)
    first_inbound_datetime = fields.Datetime(string="First Inbound Time", readonly=True, copy=False, index=True)
    project_id = fields.Many2one("project.project", string="Project", readonly=True, index=True, copy=False)
    owner_id = fields.Many2one("res.partner", string="Owner", readonly=True, index=True, copy=False)
    anomaly_message = fields.Char(string="Anomaly", readonly=True, copy=False)
