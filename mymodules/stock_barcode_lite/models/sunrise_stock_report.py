# -*- coding: utf-8 -*-

from datetime import datetime, time, timedelta

from odoo import _, fields, models
from odoo.exceptions import ValidationError


class SunriseStockReport(models.Model):
    _name = "sunrise.stock.report"
    _description = "Sunrise Stock Report"
    _order = "id desc"

    date_from = fields.Date(string="Date From", required=True, default=lambda self: fields.Date.context_today(self).replace(day=1), index=True)
    date_to = fields.Date(string="Date To", required=True, default=fields.Date.context_today, index=True)
    product_template_id = fields.Many2one("product.template", string="Product", copy=False, index=True)
    product_keyword = fields.Char(string="Product Code / Name", copy=False, index=True)
    lot_name = fields.Char(string="Lot No", copy=False, index=True)
    pallet_no = fields.Char(string="Original Pallet No", copy=False, index=True)
    state = fields.Selection([("draft", "Draft"), ("done", "Done")], string="State", default="draft", required=True, readonly=True, copy=False, index=True)
    refreshed_by_id = fields.Many2one("res.users", string="Last Refreshed By", readonly=True, copy=False)
    refreshed_datetime = fields.Datetime(string="Last Refreshed At", readonly=True, copy=False, index=True)
    line_ids = fields.One2many("sunrise.stock.report.line", "report_id", string="Report Lines", readonly=True, copy=False)

    def action_refresh_report(self):
        inbound_product_model = self.env["world.depot.inbound.order.product"].sudo()
        move_line_model = self.env["stock.move.line"].sudo()
        outbound_product_model = self.env["world.depot.outbound.order.product"].sudo()
        report_line_model = self.env["sunrise.stock.report.line"]
        action = False

        for rec in self:
            if rec.date_from > rec.date_to:
                raise ValidationError(_("Date From must not be later than Date To."))

            package_data_map = {}
            inbound_pallet_lines = inbound_product_model.search([
                ("project.name", "=", "SUNRISE"),
                ("package_id", "!=", False),
            ])
            for pallet_line in inbound_pallet_lines:
                for detail_line in pallet_line.inbound_order_product_pallet_ids:
                    package_data_map[(pallet_line.package_id.id, detail_line.product_id.id)] = {
                        "source_product_code": detail_line.source_product_code or detail_line.product_id.barcode or detail_line.product_id.default_code or "",
                        "pallet_no": pallet_line.pallet_no or "",
                    }

            package_ids = list({package_id for package_id, product_id in package_data_map})
            date_to_exclusive = datetime.combine(rec.date_to + timedelta(days=1), time.min)
            move_line_domain = [
                ("move_id.state", "=", "done"),
                ("date", "<", date_to_exclusive),
            ]
            if package_ids:
                move_line_domain += [
                    "|", "|",
                    ("picking_id.project_id.name", "=", "SUNRISE"),
                    ("package_id", "in", package_ids),
                    ("result_package_id", "in", package_ids),
                ]
            else:
                move_line_domain.append(("picking_id.project_id.name", "=", "SUNRISE"))

            move_lines = move_line_model.search(move_line_domain, order="date asc, id asc")
            report_data_map = {}
            product_keyword = (rec.product_keyword or "").strip().lower()
            lot_filter = (rec.lot_name or "").strip().lower()
            pallet_filter = (rec.pallet_no or "").strip().lower()

            for move_line in move_lines:
                inbound_detail = move_line.inbound_order_product_pallet_id
                outbound_line = outbound_product_model.browse(move_line.move_id.outbound_order_product_id)
                package = move_line.result_package_id or move_line.package_id
                package_data = package_data_map.get((package.id, move_line.product_id.id), {}) if package else {}
                product_template = move_line.product_id.product_tmpl_id
                source_product_code = (
                    inbound_detail.source_product_code
                    or outbound_line.source_product_code
                    or package_data.get("source_product_code")
                    or move_line.product_id.barcode
                    or move_line.product_id.default_code
                    or ""
                )
                pallet_no = (
                    inbound_detail.inbound_order_product_id.pallet_no
                    or outbound_line.pallet_no
                    or package_data.get("pallet_no")
                    or ""
                )
                lot_name = move_line.lot_id.name or inbound_detail.lot_name or outbound_line.lot_name or ""

                if rec.product_template_id and product_template != rec.product_template_id:
                    continue
                if product_keyword:
                    product_text = " ".join([
                        source_product_code,
                        move_line.product_id.barcode or "",
                        move_line.product_id.default_code or "",
                        product_template.name or "",
                    ]).lower()
                    if product_keyword not in product_text:
                        continue
                if lot_filter and lot_filter not in lot_name.lower():
                    continue
                if pallet_filter and pallet_filter not in pallet_no.lower():
                    continue

                source_usage = move_line.location_id.usage
                destination_usage = move_line.location_dest_id.usage
                movement_type = False
                signed_quantity = 0.0
                if source_usage == "inventory" and destination_usage == "internal":
                    movement_type = "adjustment"
                    signed_quantity = move_line.quantity
                elif source_usage == "internal" and destination_usage == "inventory":
                    movement_type = "adjustment"
                    signed_quantity = -move_line.quantity
                elif source_usage != "internal" and destination_usage == "internal":
                    movement_type = "inbound"
                    signed_quantity = move_line.quantity
                elif source_usage == "internal" and destination_usage != "internal":
                    movement_type = "outbound"
                    signed_quantity = -move_line.quantity

                if not movement_type:
                    continue

                report_key = (
                    package.id if package else False,
                    product_template.id,
                    move_line.lot_id.id if move_line.lot_id else False,
                    pallet_no if not package else False,
                )
                report_data = report_data_map.setdefault(report_key, {
                    "package_id": package.id if package else False,
                    "product_template_id": product_template.id,
                    "source_product_code": source_product_code,
                    "lot_name": lot_name,
                    "pallet_no": pallet_no,
                    "uom_id": move_line.product_uom_id.id,
                    "opening_quantity": 0.0,
                    "inbound_quantity": 0.0,
                    "outbound_quantity": 0.0,
                    "adjustment_quantity": 0.0,
                })
                move_date = move_line.date.date()
                if move_date < rec.date_from:
                    report_data["opening_quantity"] += signed_quantity
                elif movement_type == "inbound":
                    report_data["inbound_quantity"] += move_line.quantity
                elif movement_type == "outbound":
                    report_data["outbound_quantity"] += move_line.quantity
                else:
                    report_data["adjustment_quantity"] += signed_quantity

            rec.line_ids.unlink()
            line_values_list = []
            for report_data in sorted(
                report_data_map.values(),
                key=lambda data: (
                    data["source_product_code"],
                    data["lot_name"],
                    data["pallet_no"],
                    data["package_id"] or 0,
                ),
            ):
                report_data["closing_quantity"] = (
                    report_data["opening_quantity"]
                    + report_data["inbound_quantity"]
                    - report_data["outbound_quantity"]
                    + report_data["adjustment_quantity"]
                )
                report_data["report_id"] = rec.id
                line_values_list.append(report_data)
            if line_values_list:
                report_line_model.create(line_values_list)

            rec.write({
                "state": "done",
                "refreshed_by_id": self.env.user.id,
                "refreshed_datetime": fields.Datetime.now(),
            })
            action = {
                "type": "ir.actions.act_window",
                "res_model": "sunrise.stock.report",
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
                "name": _("Sunrise Inventory Report Lines"),
                "res_model": "sunrise.stock.report.line",
                "view_mode": "list",
                "domain": [("report_id", "=", rec.id)],
                "context": {"create": False, "edit": False},
                "target": "current",
            }
        return action


class SunriseStockReportLine(models.Model):
    _name = "sunrise.stock.report.line"
    _description = "Sunrise Stock Report Line"
    _order = "id desc"

    report_id = fields.Many2one("sunrise.stock.report", string="Report", required=True, ondelete="cascade", index=True, copy=False)
    package_id = fields.Many2one("stock.quant.package", string="Package", readonly=True, index=True, copy=False)
    package_barcode = fields.Char(related="package_id.barcode", string="Package Barcode", readonly=True)
    product_template_id = fields.Many2one("product.template", string="Product", required=True, readonly=True, index=True, copy=False)
    source_product_code = fields.Char(string="Source Product Code", readonly=True, index=True, copy=False)
    lot_name = fields.Char(string="Lot No", readonly=True, index=True, copy=False)
    pallet_no = fields.Char(string="Original Pallet No", readonly=True, index=True, copy=False)
    uom_id = fields.Many2one("uom.uom", string="Unit", readonly=True, copy=False)
    opening_quantity = fields.Float(string="Opening Quantity", readonly=True, copy=False)
    inbound_quantity = fields.Float(string="Inbound Quantity", readonly=True, copy=False)
    outbound_quantity = fields.Float(string="Outbound Quantity", readonly=True, copy=False)
    adjustment_quantity = fields.Float(string="Adjustment Quantity", readonly=True, copy=False)
    closing_quantity = fields.Float(string="Closing Quantity", readonly=True, copy=False)

    def action_view_move_lines(self):
        outbound_product_model = self.env["world.depot.outbound.order.product"].sudo()
        action = False

        for rec in self:
            date_to_exclusive = datetime.combine(rec.report_id.date_to + timedelta(days=1), time.min)
            domain = [
                ("move_id.state", "=", "done"),
                ("date", ">=", datetime.combine(rec.report_id.date_from, time.min)),
                ("date", "<", date_to_exclusive),
                ("product_id.product_tmpl_id", "=", rec.product_template_id.id),
            ]
            if rec.lot_name:
                domain.append(("lot_id.name", "=", rec.lot_name))
            else:
                domain.append(("lot_id", "=", False))
            if rec.package_id:
                domain += [
                    "|",
                    ("package_id", "=", rec.package_id.id),
                    ("result_package_id", "=", rec.package_id.id),
                ]
            else:
                outbound_lines = outbound_product_model.search([
                    ("outbound_order_id.project.name", "=", "SUNRISE"),
                    ("pallet_no", "=", rec.pallet_no),
                ])
                domain += [
                    "|",
                    ("inbound_order_product_pallet_id.inbound_order_product_id.pallet_no", "=", rec.pallet_no),
                    ("move_id.outbound_order_product_id", "in", outbound_lines.ids),
                ]
            action = {
                "type": "ir.actions.act_window",
                "name": _("Stock Moves"),
                "res_model": "stock.move.line",
                "view_mode": "list,form",
                "domain": domain,
                "context": {"create": False, "edit": False},
                "target": "current",
            }
        return action
