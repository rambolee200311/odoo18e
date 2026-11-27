# -*- coding: utf-8 -*-

import base64
import io
from datetime import timedelta

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockPalletDetailReport(models.Model):
    _name = "stock.pallet.detail.report"
    _description = "Pallet Detail Stock Report"
    _order = "id desc"

    name = fields.Char(string="Name", compute="_compute_name", store=True, readonly=True, copy=False, index=True)
    project_id = fields.Many2one("project.project", string="Project", required=True, ondelete="restrict", copy=False, index=True)
    date_from = fields.Date(string="Date From", required=True, default=lambda self: fields.Date.context_today(self).replace(day=1), copy=False, index=True)
    date_to = fields.Date(string="Date To", required=True, default=fields.Date.context_today, copy=False, index=True)
    location_id = fields.Many2one("stock.location", string="Location", domain=[("usage", "=", "internal")], ondelete="restrict", copy=False, index=True)
    state = fields.Selection([("draft", "Draft"), ("done", "Done")], string="State", default="draft", required=True, readonly=True, copy=False, index=True)
    refreshed_by_id = fields.Many2one("res.users", string="Last Refreshed By", readonly=True, copy=False, index=True)
    refreshed_datetime = fields.Datetime(string="Last Refreshed At", readonly=True, copy=False, index=True)
    opening_pallet_count = fields.Integer(string="Opening Pallets", readonly=True, copy=False)
    inbound_pallet_count = fields.Integer(string="Inbound Pallets", readonly=True, copy=False)
    outbound_pallet_count = fields.Integer(string="Outbound Pallets", readonly=True, copy=False)
    closing_pallet_count = fields.Integer(string="Closing Pallets", readonly=True, copy=False)
    line_ids = fields.One2many("stock.pallet.detail.report.line", "report_id", string="Detail Lines", readonly=True, copy=False)

    warehouse_id = fields.Many2one("stock.warehouse", string="Warehouse", required=True, ondelete="restrict", copy=False, index=True)

    @api.depends("project_id", "warehouse_id", "date_from", "date_to")
    def _compute_name(self):
        for rec in self:
            rec.name = "%s - %s - %s ~ %s" % (rec.project_id.display_name or "", rec.warehouse_id.display_name or "", rec.date_from or "", rec.date_to or "")

    def action_refresh_report(self):
        move_line_model = self.env["stock.move.line"].sudo()
        package_model = self.env["stock.quant.package"].sudo()
        inbound_order_model = self.env["world.depot.inbound.order"].sudo()
        report_line_model = self.env["stock.pallet.detail.report.line"]
        stock_line_model = self.env["stock.pallet.detail.report.stock.line"]
        operation_line_model = self.env["stock.pallet.detail.report.operation.line"]
        action = False

        for rec in self:
            if rec.date_from > rec.date_to:
                raise ValidationError(_("Date From must not be later than Date To."))
            location_id = rec.location_id or rec.warehouse_id.view_location_id
            report_data = move_line_model.get_package_movement_history({"project_id": rec.project_id.id, "warehouse_id": rec.warehouse_id.id, "date_from": rec.date_from, "date_to": rec.date_to, "location_id": location_id.id or False, "timezone": self.env.user.tz or "UTC", "use_actual_datetime": True, "reconcile_current_quant": True})
            rec.line_ids.unlink()
            row_data_list = []
            line_values_list = []
            for row in report_data["movement_rows"]:
                package = package_model.browse(row["package_id"]) if row["package_id"] else package_model
                inbound_order = inbound_order_model.browse(row["first_inbound_order_id"]) if row["first_inbound_order_id"] else inbound_order_model
                lifecycle_start_datetime = fields.Datetime.to_datetime(row["lifecycle_start_datetime"]) if row["lifecycle_start_datetime"] else False
                consumed_datetime = fields.Datetime.to_datetime(row["consumed_datetime"]) if row["consumed_datetime"] else False
                storage_week_count = 0
                if lifecycle_start_datetime:
                    start_date = fields.Datetime.context_timestamp(rec, lifecycle_start_datetime).date()
                    end_date = fields.Datetime.context_timestamp(rec, consumed_datetime).date() if consumed_datetime else rec.date_to if row["lifecycle_state"] == "consumed" else fields.Datetime.context_timestamp(rec, fields.Datetime.now()).date()
                    start_week_date = start_date - timedelta(days=start_date.weekday())
                    end_week_date = end_date - timedelta(days=end_date.weekday())
                    storage_week_count = max(1, (end_week_date - start_week_date).days // 7 + 1)
                line_values_list.append({
                    "report_id": rec.id,
                    "row_type": row["row_type"],
                    "package_id": package.id,
                    "inbound_reference": inbound_order.reference or inbound_order.billno or "",
                    "product_id": row["product_id"],
                    "product_name": row["product_name"],
                    "lot_name": row["lot_name"],
                    "uom_name": row["uom_name"],
                    "lot_summary": row["lot_summary"],
                    "closing_location_name": row["closing_location_name"],
                    "lifecycle_state": row["lifecycle_state"],
                    "lifecycle_start_datetime": lifecycle_start_datetime,
                    "consumed_datetime": consumed_datetime,
                    "storage_week_count": storage_week_count,
                    "anomaly_message": row["anomaly_message"],
                    "opening_pallet_count": row["opening_pallet_count"],
                    "inbound_pallet_count": row["inbound_pallet_count"],
                    "outbound_pallet_count": row["outbound_pallet_count"],
                    "closing_pallet_count": row["closing_pallet_count"],
                    "opening_product_summary": sum(stock_line["opening_quantity"] for stock_line in row["stock_line_ids"]),
                    "inbound_product_summary": sum(stock_line["inbound_quantity"] for stock_line in row["stock_line_ids"]),
                    "outbound_product_summary": sum(stock_line["outbound_quantity"] for stock_line in row["stock_line_ids"]),
                    "closing_product_summary": sum(stock_line["on_hand_quantity"] for stock_line in row["stock_line_ids"]),
                })
                row_data_list.append(row)
            report_lines = report_line_model.create(line_values_list) if line_values_list else report_line_model
            stock_values_list = []
            operation_values_list = []
            for report_line, row in zip(report_lines, row_data_list):
                for stock_line in row["stock_line_ids"]:
                    stock_values_list.append(dict(stock_line, report_line_id=report_line.id))
                for operation_line in row["operation_line_ids"]:
                    operation_values_list.append(dict(operation_line, report_line_id=report_line.id))
            if stock_values_list:
                stock_line_model.create(stock_values_list)
            if operation_values_list:
                operation_line_model.create(operation_values_list)
            rec.write({
                "state": "done",
                "refreshed_by_id": self.env.user.id,
                "refreshed_datetime": fields.Datetime.now(),
                "opening_pallet_count": sum(row["opening_pallet_count"] for row in row_data_list),
                "inbound_pallet_count": sum(row["inbound_pallet_count"] for row in row_data_list),
                "outbound_pallet_count": sum(row["outbound_pallet_count"] for row in row_data_list),
                "closing_pallet_count": sum(row["closing_pallet_count"] for row in row_data_list),
            })
            action = {"type": "ir.actions.act_window", "res_model": rec._name, "res_id": rec.id, "view_mode": "form", "target": "current"}
        return action

    def action_view_report_lines(self):
        action = False
        for rec in self:
            action = {"type": "ir.actions.act_window", "name": _("Pallet Detail Stock Report Lines"), "res_model": "stock.pallet.detail.report.line", "view_mode": "list,form", "domain": [("report_id", "=", rec.id)], "context": {"create": False, "edit": False}, "target": "current"}
        return action

    def action_export_excel(self):
        report_line_model = self.env["stock.pallet.detail.report.line"].sudo()
        stock_line_model = self.env["stock.pallet.detail.report.stock.line"].sudo()
        operation_line_model = self.env["stock.pallet.detail.report.operation.line"].sudo()
        attachment_model = self.env["ir.attachment"]
        action = False

        for rec in self:
            if rec.state != "done":
                raise ValidationError(_("Please refresh the report before exporting."))
            export_type = self.env.context.get("export_type")
            if export_type == "summary":
                sheet_name = "Summary"
                file_prefix = "Pallet_Detail_Stock_Summary"
                headers = ["Row Type", "Package", "Inbound Reference", "Product", "SN / Lot", "Lifecycle Start", "Consumed At", "Storage Weeks", "Cutoff / Last Location", "Lifecycle State", "Anomaly", "Opening Quantity", "Inbound Quantity", "Outbound Quantity", "Closing Quantity"]
                row_type_label_map = dict(report_line_model._fields["row_type"].selection)
                state_label_map = dict(report_line_model._fields["lifecycle_state"].selection)
                report_lines = report_line_model.search([("report_id", "=", rec.id)], order="id")
                rows = [[row_type_label_map.get(line.row_type, ""), line.package_id.name or "", line.inbound_reference or "", line.product_name or "", line.lot_name or line.lot_summary or "", fields.Datetime.context_timestamp(rec, line.lifecycle_start_datetime).strftime("%Y-%m-%d %H:%M:%S") if line.lifecycle_start_datetime else "", fields.Datetime.context_timestamp(rec, line.consumed_datetime).strftime("%Y-%m-%d %H:%M:%S") if line.consumed_datetime else "", line.storage_week_count, line.closing_location_name or "", state_label_map.get(line.lifecycle_state, ""), line.anomaly_message or "", line.opening_product_summary, line.inbound_product_summary, line.outbound_product_summary, line.closing_product_summary] for line in report_lines]
            elif export_type == "stock":
                sheet_name = "Stock Details"
                file_prefix = "Pallet_Detail_Stock_Details"
                headers = ["Row Type", "Package", "Inbound Reference", "Product", "Product Code", "SN / Lot", "Unit", "Cutoff / Last Location", "Opening Quantity", "Inbound Quantity", "Outbound Quantity", "Closing Quantity", "Reserved Quantity", "Available Quantity", "Reservation Note"]
                row_type_label_map = dict(report_line_model._fields["row_type"].selection)
                stock_lines = stock_line_model.search([("report_line_id.report_id", "=", rec.id)], order="report_line_id, product_id, lot_id, id")
                rows = [[row_type_label_map.get(line.report_line_id.row_type, ""), line.report_line_id.package_id.name or "", line.report_line_id.inbound_reference or "", line.product_name or "", line.product_code or "", line.lot_name or "", line.uom_name or "", line.closing_location_name or "", line.opening_quantity, line.inbound_quantity, line.outbound_quantity, line.on_hand_quantity, line.reserved_quantity, line.available_quantity, line.reservation_note or ""] for line in stock_lines]
            elif export_type == "operation":
                sheet_name = "Operations"
                file_prefix = "Pallet_Detail_Stock_Operations"
                headers = ["Row Type", "Package", "Inbound Reference", "Direction", "Operation Datetime", "Inbound Order", "Outbound Order", "Picking", "Picking State", "Product", "Product Code", "SN / Lot", "Planned Quantity", "Reserved Quantity", "Done Quantity", "Unit", "Source Location", "Destination Location"]
                row_type_label_map = dict(report_line_model._fields["row_type"].selection)
                direction_label_map = dict(operation_line_model._fields["direction"].selection)
                operation_lines = operation_line_model.search([("report_line_id.report_id", "=", rec.id)], order="operation_datetime desc, id desc")
                rows = [[row_type_label_map.get(line.report_line_id.row_type, ""), line.report_line_id.package_id.name or "", line.report_line_id.inbound_reference or "", direction_label_map.get(line.direction, ""), fields.Datetime.context_timestamp(rec, line.operation_datetime).strftime("%Y-%m-%d %H:%M:%S") if line.operation_datetime else "", line.inbound_order_name or "", line.outbound_order_name or "", line.picking_name or "", line.picking_state or "", line.product_name or "", line.product_code or "", line.lot_name or "", line.planned_quantity, line.reserved_quantity, line.done_quantity, line.uom_name or "", line.source_location_name or "", line.destination_location_name or ""] for line in operation_lines]
            else:
                raise ValidationError(_("Unsupported Excel export type."))
            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output, {"in_memory": True})
            worksheet = workbook.add_worksheet(sheet_name)
            title_format = workbook.add_format({"bold": True, "font_size": 14, "align": "center", "valign": "vcenter"})
            label_format = workbook.add_format({"bold": True, "border": 1})
            value_format = workbook.add_format({"border": 1})
            header_format = workbook.add_format({"bold": True, "align": "center", "valign": "vcenter", "text_wrap": True, "bg_color": "#D9EAF7", "border": 1})
            text_format = workbook.add_format({"border": 1, "valign": "vcenter", "text_wrap": True})
            number_format = workbook.add_format({"border": 1, "valign": "vcenter", "align": "right", "num_format": "0.00"})
            worksheet.merge_range(0, 0, 0, len(headers) - 1, "%s - %s" % (sheet_name, rec.name or ""), title_format)
            worksheet.write(1, 0, "Project", label_format)
            worksheet.merge_range(1, 1, 1, 3, rec.project_id.display_name or "", value_format)
            worksheet.write(2, 0, "Period", label_format)
            worksheet.merge_range(2, 1, 2, 3, "%s to %s" % (rec.date_from or "", rec.date_to or ""), value_format)
            worksheet.write(3, 0, "Location", label_format)
            worksheet.merge_range(3, 1, 3, 3, rec.location_id.complete_name or rec.warehouse_id.view_location_id.complete_name or _("All Internal Locations"), value_format)
            worksheet.write_row(5, 0, headers, header_format)
            worksheet.freeze_panes(6, 0)
            worksheet.autofilter(5, 0, 5 + len(rows), len(headers) - 1)
            worksheet.set_column(0, len(headers) - 1, 18)
            for row_index, row in enumerate(rows, start=6):
                for column_index, value in enumerate(row):
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        worksheet.write_number(row_index, column_index, value, number_format)
                    else:
                        worksheet.write(row_index, column_index, value or "", text_format)
            workbook.close()
            output.seek(0)
            attachment = attachment_model.create({"name": "%s_%s.xlsx" % (file_prefix, rec.name or rec.id), "type": "binary", "datas": base64.b64encode(output.read()), "res_model": rec._name, "res_id": rec.id, "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"})
            action = {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % attachment.id, "target": "self"}
        return action


class StockPalletDetailReportLine(models.Model):
    _name = "stock.pallet.detail.report.line"
    _description = "Pallet Detail Stock Report Line"
    _order = "id desc"

    report_id = fields.Many2one("stock.pallet.detail.report", string="Report", required=True, readonly=True, ondelete="cascade", copy=False, index=True)
    row_type = fields.Selection([("package", "Pallet"), ("loose", "Loose Goods / SN")], string="Row Type", required=True, readonly=True, copy=False, index=True)
    package_id = fields.Many2one("stock.quant.package", string="Package", readonly=True, ondelete="restrict", copy=False, index=True)
    inbound_reference = fields.Char(string="Inbound Reference", readonly=True, copy=False, index=True)
    product_id = fields.Many2one("product.product", string="Product", readonly=True, ondelete="restrict", copy=False, index=True)
    product_name = fields.Char(string="Product Name", readonly=True, copy=False)
    lot_name = fields.Char(string="SN / Lot", readonly=True, copy=False, index=True)
    uom_name = fields.Char(string="Unit", readonly=True, copy=False)
    lot_summary = fields.Char(string="SN / Lot Summary", readonly=True, copy=False)
    closing_location_name = fields.Char(string="Cutoff / Last Location", readonly=True, copy=False)
    lifecycle_state = fields.Selection([("active", "Active"), ("consumed", "Consumed")], string="Lifecycle State", readonly=True, copy=False, index=True)
    lifecycle_start_datetime = fields.Datetime(string="Lifecycle Start", readonly=True, copy=False, index=True)
    consumed_datetime = fields.Datetime(string="Consumed At", readonly=True, copy=False, index=True)
    storage_week_count = fields.Integer(string="Storage Weeks", readonly=True, copy=False)
    anomaly_message = fields.Char(string="Anomaly", readonly=True, copy=False)
    opening_pallet_count = fields.Integer(string="Opening Pallets", readonly=True, copy=False)
    inbound_pallet_count = fields.Integer(string="Inbound Pallets", readonly=True, copy=False)
    outbound_pallet_count = fields.Integer(string="Outbound Pallets", readonly=True, copy=False)
    closing_pallet_count = fields.Integer(string="Closing Pallets", readonly=True, copy=False)
    opening_product_summary = fields.Float(string="Opening Product Quantity", readonly=True, copy=False)
    inbound_product_summary = fields.Float(string="Inbound Product Quantity", readonly=True, copy=False)
    outbound_product_summary = fields.Float(string="Outbound Product Quantity", readonly=True, copy=False)
    closing_product_summary = fields.Float(string="Closing Product Quantity", readonly=True, copy=False)
    stock_line_ids = fields.One2many("stock.pallet.detail.report.stock.line", "report_line_id", string="Stock Lines", readonly=True, copy=False)
    operation_line_ids = fields.One2many("stock.pallet.detail.report.operation.line", "report_line_id", string="Operation Lines", readonly=True, copy=False)

class StockPalletDetailReportStockLine(models.Model):
    _name = "stock.pallet.detail.report.stock.line"
    _description = "Pallet Detail Stock Line"
    _order = "id desc"

    report_line_id = fields.Many2one("stock.pallet.detail.report.line", string="Detail Line", required=True, readonly=True, ondelete="cascade", copy=False, index=True)
    product_id = fields.Many2one("product.product", string="Product", required=True, readonly=True, ondelete="restrict", copy=False, index=True)
    product_name = fields.Char(string="Product Name", readonly=True, copy=False)
    product_code = fields.Char(string="Product Code", readonly=True, copy=False)
    lot_id = fields.Many2one("stock.lot", string="SN / Lot", readonly=True, ondelete="restrict", copy=False, index=True)
    lot_name = fields.Char(string="SN / Lot Name", readonly=True, copy=False, index=True)
    uom_name = fields.Char(string="Unit", readonly=True, copy=False)
    closing_location_name = fields.Char(string="Cutoff / Last Location", readonly=True, copy=False)
    opening_quantity = fields.Float(string="Opening Quantity", readonly=True, copy=False)
    inbound_quantity = fields.Float(string="Inbound Quantity", readonly=True, copy=False)
    outbound_quantity = fields.Float(string="Outbound Quantity", readonly=True, copy=False)
    on_hand_quantity = fields.Float(string="Closing Quantity", readonly=True, copy=False)
    reserved_quantity = fields.Float(string="Reserved Quantity", readonly=True, copy=False)
    available_quantity = fields.Float(string="Available Quantity", readonly=True, copy=False)
    reservation_note = fields.Char(string="Reservation Note", readonly=True, copy=False)


class StockPalletDetailReportOperationLine(models.Model):
    _name = "stock.pallet.detail.report.operation.line"
    _description = "Pallet Detail Stock Operation Line"
    _order = "operation_datetime desc, id desc"

    report_line_id = fields.Many2one("stock.pallet.detail.report.line", string="Detail Line", required=True, readonly=True, ondelete="cascade", copy=False, index=True)
    direction = fields.Selection([("inbound", "Inbound"), ("outbound", "Outbound")], string="Direction", required=True, readonly=True, copy=False, index=True)
    inbound_order_id = fields.Many2one("world.depot.inbound.order", string="Inbound Order", readonly=True, ondelete="restrict", copy=False, index=True)
    inbound_order_name = fields.Char(string="Inbound Order Name", readonly=True, copy=False)
    outbound_order_id = fields.Many2one("world.depot.outbound.order", string="Outbound Order", readonly=True, ondelete="restrict", copy=False, index=True)
    outbound_order_name = fields.Char(string="Outbound Order Name", readonly=True, copy=False)
    picking_id = fields.Many2one("stock.picking", string="Picking", readonly=True, ondelete="restrict", copy=False, index=True)
    picking_name = fields.Char(string="Picking Name", readonly=True, copy=False)
    picking_state = fields.Char(string="Picking State", readonly=True, copy=False)
    product_id = fields.Many2one("product.product", string="Product", readonly=True, ondelete="restrict", copy=False, index=True)
    product_name = fields.Char(string="Product Name", readonly=True, copy=False)
    product_code = fields.Char(string="Product Code", readonly=True, copy=False)
    lot_id = fields.Many2one("stock.lot", string="SN / Lot", readonly=True, ondelete="restrict", copy=False, index=True)
    lot_name = fields.Char(string="SN / Lot Name", readonly=True, copy=False, index=True)
    planned_quantity = fields.Float(string="Planned Quantity", readonly=True, copy=False)
    reserved_quantity = fields.Float(string="Reserved Quantity", readonly=True, copy=False)
    done_quantity = fields.Float(string="Done Quantity", readonly=True, copy=False)
    uom_name = fields.Char(string="Unit", readonly=True, copy=False)
    operation_datetime = fields.Datetime(string="Operation Datetime", required=True, readonly=True, copy=False, index=True)
    source_location_name = fields.Char(string="Source Location", readonly=True, copy=False)
    destination_location_name = fields.Char(string="Destination Location", readonly=True, copy=False)
