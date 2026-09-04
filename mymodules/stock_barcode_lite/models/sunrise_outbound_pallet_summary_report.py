# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import datetime, time, timedelta

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
    cprojectid = fields.Char(string="Sunrise Ref", copy=False, index=True)
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

        for rec in self:
            if rec.state == "done":
                raise ValidationError(_("A refreshed report cannot be refreshed again."))
            if rec.date_from > rec.date_to:
                raise ValidationError(_("Date From must not be later than Date To."))

            sunrise_project = project_model.search([("name", "=", "SUNRISE")], limit=1)
            if not sunrise_project:
                raise ValidationError(_("SUNRISE project was not found."))
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

            date_from_datetime = datetime.combine(rec.date_from, time.min)
            date_to_exclusive = datetime.combine(rec.date_to + timedelta(days=1), time.min)
            outbound_move_lines = move_line_model.search([
                ("state", "=", "done"),
                ("date", ">=", date_from_datetime),
                ("date", "<", date_to_exclusive),
                ("picking_id.state", "=", "done"),
                ("picking_id.picking_type_id.code", "=", "outgoing"),
                ("picking_id.outbound_order_id.project", "=", sunrise_project.id),
                ("location_id.usage", "=", "internal"),
                ("location_dest_id.usage", "!=", "internal"),
            ], order="date asc, id asc")
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
                    "outbound_datetime": move_line.date,
                    "cprojectid_set": set(),
                    "product_name_set": {format_product_template_name(line.product_id.product_tmpl_id) for line in outbound_order_product_lines if line.product_id and line.product_id.product_tmpl_id},
                    "product_quantity_total": sum(line.quantity or 0.0 for line in outbound_order_product_lines),
                    "pallet_data_map": {},
                })
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

            cprojectid_keyword = (rec.cprojectid or "").strip().lower()
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
                inbound_move_lines = move_line_model.search([
                    ("state", "=", "done"),
                    ("date", "<", date_to_exclusive),
                    ("picking_id.state", "=", "done"),
                    ("picking_id.picking_type_id.code", "=", "incoming"),
                    ("result_package_id", "in", package_ids),
                    ("location_id.usage", "!=", "internal"),
                    ("location_dest_id.usage", "=", "internal"),
                ], order="date asc, id asc")
                for move_line in inbound_move_lines:
                    package_id = move_line.result_package_id.id
                    inbound_data = package_inbound_data_map.setdefault(package_id, {
                        "inbound_datetime": move_line.date,
                        "inbound_picking_id": move_line.picking_id.id,
                        "inbound_quantity_total": 0.0,
                    })
                    if move_line.date < inbound_data["inbound_datetime"]:
                        inbound_data["inbound_datetime"] = move_line.date
                        inbound_data["inbound_picking_id"] = move_line.picking_id.id
                        inbound_data["inbound_quantity_total"] = 0.0
                    if move_line.picking_id.id == inbound_data["inbound_picking_id"]:
                        inbound_data["inbound_quantity_total"] += move_line.quantity

            package_consumed_datetime_map = {}
            if package_ids:
                package_move_lines = move_line_model.search([
                    ("state", "=", "done"),
                    ("date", "<", date_to_exclusive),
                    "|",
                    ("package_id", "in", package_ids),
                    ("result_package_id", "in", package_ids),
                ], order="date asc, id asc")
                package_quantity_map = defaultdict(lambda: defaultdict(float))
                for move_line in package_move_lines:
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
                            package_consumed_datetime_map[package_id] = move_line.date

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


class SunriseOutboundPalletSummaryReportLine(models.Model):
    _name = "sunrise.outbound.pallet.summary.report.line"
    _description = "Sunrise Outbound Pallet Summary Report Line"
    _order = "id desc"

    report_id = fields.Many2one("sunrise.outbound.pallet.summary.report", string="Report", required=True, readonly=True, ondelete="cascade", index=True, copy=False)
    outbound_order_id = fields.Many2one("world.depot.outbound.order", string="Outbound Order", required=True, readonly=True, ondelete="restrict", index=True, copy=False)
    order_date = fields.Date(string="Order Date", readonly=True, index=True, copy=False)
    sunrise_ref = fields.Char(string="Sunrise Ref", readonly=True, copy=False)
    outbound_datetime = fields.Datetime(string="Outbound Datetime", required=True, readonly=True, index=True, copy=False)
    system_document_no = fields.Char(string="Outbound No", readonly=True, copy=False)
    outbound_pallet_count = fields.Integer(string="Outbound Pallets", readonly=True, copy=False)
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
    sunrise_ref = fields.Char(string="Sunrise Ref", readonly=True, copy=False)
    product_names = fields.Char(string="Products", readonly=True, copy=False)
    inbound_quantity_summary = fields.Float(string="Inbound Product Quantity", readonly=True, copy=False)
    outbound_quantity = fields.Float(string="Outbound Product Quantity", readonly=True, copy=False)
    inbound_datetime = fields.Datetime(string="Inbound Datetime", readonly=True, index=True, copy=False)
    consumed_datetime = fields.Datetime(string="Fully Outbound Datetime", readonly=True, index=True, copy=False)
    location_summary = fields.Char(string="Outbound Location", readonly=True, copy=False)
