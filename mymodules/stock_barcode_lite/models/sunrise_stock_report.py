# -*- coding: utf-8 -*-

import base64
import io
from collections import defaultdict
from datetime import datetime, time, timedelta

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SunriseStockReport(models.Model):
    _name = "sunrise.stock.report"
    _description = "Sunrise Pallet Aging Report"
    _order = "id desc"

    name = fields.Char(string="Name", compute="_compute_name", store=True, readonly=True, copy=False, index=True)
    date_from = fields.Date(string="Date From", required=True, default=lambda self: fields.Date.context_today(self).replace(day=1), index=True)
    date_to = fields.Date(string="Date To", required=True, default=fields.Date.context_today, index=True)
    warehouse_id = fields.Many2one("stock.warehouse", string="Warehouse", copy=False, index=True)
    owner_id = fields.Many2one("res.partner", string="Owner", copy=False, index=True)
    product_template_id = fields.Many2one("product.template", string="Product", copy=False, index=True)
    lot_name = fields.Char(string="Lot No", copy=False, index=True)
    state = fields.Selection([("draft", "Draft"), ("done", "Done")], string="State", default="draft", required=True, readonly=True, copy=False, index=True)
    refreshed_by_id = fields.Many2one("res.users", string="Last Refreshed By", readonly=True, copy=False)
    refreshed_datetime = fields.Datetime(string="Last Refreshed At", readonly=True, copy=False, index=True)
    average_age_days = fields.Float(string="Closing Average Age Days", readonly=True, copy=False)
    maximum_age_days = fields.Integer(string="Maximum Age Days", readonly=True, copy=False)
    over_180_pallet_count = fields.Integer(string="Over 180 Days Pallets", readonly=True, copy=False)
    line_ids = fields.One2many("sunrise.stock.report.line", "report_id", string="Pallet Summary Lines", readonly=True, copy=False)

    @api.depends("date_from", "date_to")
    def _compute_name(self):
        for rec in self:
            rec.name = "%s ~ %s" % (rec.date_from or "", rec.date_to or "")

    def action_refresh_report(self):
        inbound_move_line_model = self.env["stock.move.line"].sudo()
        move_line_model = self.env["stock.move.line"].sudo()
        quant_model = self.env["stock.quant"].sudo()
        outbound_product_model = self.env["world.depot.outbound.order.product"].sudo()
        report_line_model = self.env["sunrise.stock.report.line"]
        stock_line_model = self.env["sunrise.stock.report.product.line"]
        operation_line_model = self.env["sunrise.stock.report.operation.line"]
        action = False

        for rec in self:
            if rec.state == "done":
                raise ValidationError(_("A refreshed report cannot be refreshed again."))
            if rec.date_from > rec.date_to:
                raise ValidationError(_("Date From must not be later than Date To."))

            date_to_exclusive = datetime.combine(rec.date_to + timedelta(days=1), time.min)
            inbound_move_lines = inbound_move_line_model.search([
                ("move_id.state", "=", "done"),
                ("date", "<", date_to_exclusive),
                ("picking_id.picking_type_id.code", "=", "incoming"),
                ("picking_id.inbound_order_id.project.name", "=", "SUNRISE"),
                ("result_package_id", "!=", False),
            ], order="date asc, id asc")
            package_data_map = {}
            for move_line in inbound_move_lines:
                package = move_line.result_package_id
                inbound_order = move_line.picking_id.inbound_order_id
                inbound_detail = move_line.inbound_order_product_pallet_id
                warehouse = inbound_order.warehouse or move_line.picking_id.picking_type_id.warehouse_id
                pallet_no = inbound_detail.inbound_order_product_id.pallet_no if inbound_detail else ""
                package_data = package_data_map.setdefault(package.id, {
                    "package": package,
                    "warehouse": warehouse,
                    "owner": inbound_order.owner,
                    "pallet_no": pallet_no or "",
                })
                if not package_data["pallet_no"] and pallet_no:
                    package_data["pallet_no"] = pallet_no

            candidate_package_ids = []
            for package_id, package_data in package_data_map.items():
                if rec.warehouse_id and package_data["warehouse"] != rec.warehouse_id:
                    continue
                if rec.owner_id and package_data["owner"] != rec.owner_id:
                    continue
                candidate_package_ids.append(package_id)

            if not candidate_package_ids:
                rec.line_ids.unlink()
                rec.write({
                    "state": "done",
                    "refreshed_by_id": self.env.user.id,
                    "refreshed_datetime": fields.Datetime.now(),
                    "average_age_days": 0.0,
                    "maximum_age_days": 0,
                    "over_180_pallet_count": 0,
                })
                action = {
                    "type": "ir.actions.act_window",
                    "res_model": "sunrise.stock.report",
                    "res_id": rec.id,
                    "view_mode": "form",
                    "views": [(False, "form")],
                    "target": "current",
                }
                continue

            move_lines = move_line_model.search([
                ("move_id.state", "=", "done"),
                ("date", "<", date_to_exclusive),
                "|",
                ("package_id", "in", candidate_package_ids),
                ("result_package_id", "in", candidate_package_ids),
            ], order="date asc, id asc")
            pending_move_lines = move_line_model.search([
                ("move_id.state", "not in", ("done", "cancel")),
                ("picking_id.state", "not in", ("done", "cancel")),
                ("picking_id.picking_type_id.code", "in", ("incoming", "outgoing")),
                "|",
                ("package_id", "in", candidate_package_ids),
                ("result_package_id", "in", candidate_package_ids),
            ], order="date asc, id asc")
            current_quant_map = defaultdict(float)
            if rec.date_to == fields.Date.context_today(rec):
                quants = quant_model.search([
                    ("package_id", "in", candidate_package_ids),
                    ("location_id.usage", "=", "internal"),
                ])
                for quant in quants:
                    current_quant_map[(quant.package_id.id, quant.product_id.id, quant.lot_id.id)] += quant.reserved_quantity

            package_event_map = defaultdict(list)
            product_map = {}
            lot_map = {}
            for move_line in move_lines:
                source_usage = move_line.location_id.usage
                destination_usage = move_line.location_dest_id.usage
                direction = False
                signed_quantity = 0.0
                package = False
                if source_usage == "inventory" and destination_usage == "internal":
                    direction = "adjustment"
                    signed_quantity = move_line.quantity
                    package = move_line.result_package_id or move_line.package_id
                elif source_usage == "internal" and destination_usage == "inventory":
                    direction = "adjustment"
                    signed_quantity = -move_line.quantity
                    package = move_line.package_id or move_line.result_package_id
                elif source_usage != "internal" and destination_usage == "internal":
                    direction = "inbound"
                    signed_quantity = move_line.quantity
                    package = move_line.result_package_id or move_line.package_id
                elif source_usage == "internal" and destination_usage != "internal":
                    direction = "outbound"
                    signed_quantity = -move_line.quantity
                    package = move_line.package_id or move_line.result_package_id
                elif source_usage == "internal" and destination_usage == "internal":
                    direction = "internal"
                    package = move_line.package_id or move_line.result_package_id

                if not package or package.id not in candidate_package_ids or not direction:
                    continue
                product_map[move_line.product_id.id] = move_line.product_id
                if move_line.lot_id:
                    lot_map[move_line.lot_id.id] = move_line.lot_id
                package_event_map[package.id].append({
                    "move_line": move_line,
                    "date": move_line.date,
                    "direction": direction,
                    "signed_quantity": signed_quantity,
                    "package": package,
                })

            pending_operation_map = defaultdict(list)
            for move_line in pending_move_lines:
                source_usage = move_line.location_id.usage
                destination_usage = move_line.location_dest_id.usage
                if source_usage != "internal" and destination_usage == "internal":
                    direction = "inbound"
                    package = move_line.result_package_id or move_line.package_id
                elif source_usage == "internal" and destination_usage != "internal":
                    direction = "outbound"
                    package = move_line.package_id or move_line.result_package_id
                else:
                    continue
                if not package or package.id not in candidate_package_ids:
                    continue
                pending_operation_map[package.id].append({
                    "move_line": move_line,
                    "direction": direction,
                    "package": package,
                })

            lot_filter = (rec.lot_name or "").strip().lower()
            line_data_map = {}
            closing_age_days_list = []
            for package_id in candidate_package_ids:
                package_data = package_data_map[package_id]
                package_events = package_event_map[package_id]
                if not package_events:
                    continue

                product_lot_quantity_map = defaultdict(float)
                product_lot_period_map = defaultdict(lambda: {"opening_quantity": 0.0, "inbound_quantity": 0.0, "outbound_quantity": 0.0})
                lifecycle_start_datetime = False
                lifecycle_start_move_line = False
                consumed_datetime = False
                lifecycle_count = 0
                opening_pallet_count = 0
                inbound_pallet_count = 0
                outbound_cleared_in_period = False
                period_has_event = False
                opening_set = False
                package_matches_filter = not (rec.product_template_id or lot_filter)

                for package_event in package_events:
                    move_line = package_event["move_line"]
                    product_template = move_line.product_id.product_tmpl_id
                    move_lot_name = move_line.lot_id.name or ""
                    if (
                        (not rec.product_template_id or product_template == rec.product_template_id)
                        and (not lot_filter or lot_filter in move_lot_name.lower())
                    ):
                        package_matches_filter = True

                    event_date = package_event["date"].date()
                    if event_date >= rec.date_from and not opening_set:
                        opening_pallet_count = 1 if any(quantity > 0.000001 for quantity in product_lot_quantity_map.values()) else 0
                        opening_set = True

                    before_active = any(quantity > 0.000001 for quantity in product_lot_quantity_map.values())
                    if package_event["signed_quantity"]:
                        quantity_key = (move_line.product_id.id, move_line.lot_id.id)
                        product_lot_quantity_map[quantity_key] += package_event["signed_quantity"]
                        period_data = product_lot_period_map[quantity_key]
                        if event_date < rec.date_from:
                            period_data["opening_quantity"] += package_event["signed_quantity"]
                        elif package_event["direction"] == "inbound":
                            period_data["inbound_quantity"] += package_event["signed_quantity"]
                        elif package_event["direction"] == "outbound":
                            period_data["outbound_quantity"] -= package_event["signed_quantity"]
                    after_active = any(quantity > 0.000001 for quantity in product_lot_quantity_map.values())
                    if not before_active and after_active:
                        lifecycle_count += 1
                        lifecycle_start_datetime = package_event["date"]
                        lifecycle_start_move_line = move_line
                        consumed_datetime = False
                        if event_date >= rec.date_from and package_event["direction"] == "inbound":
                            inbound_pallet_count = 1
                    elif before_active and not after_active:
                        consumed_datetime = package_event["date"]
                        if event_date >= rec.date_from and package_event["direction"] == "outbound":
                            outbound_cleared_in_period = True

                    if event_date >= rec.date_from:
                        period_has_event = True

                if not opening_set:
                    opening_pallet_count = 1 if any(quantity > 0.000001 for quantity in product_lot_quantity_map.values()) else 0
                closing_pallet_count = 1 if any(quantity > 0.000001 for quantity in product_lot_quantity_map.values()) else 0
                if not opening_pallet_count and not period_has_event:
                    continue
                if not package_matches_filter:
                    continue

                closing_age_days = 0
                opening_age_days = 0
                period_stock_days = 0
                if lifecycle_start_datetime:
                    lifecycle_start_date = lifecycle_start_datetime.date()
                    if opening_pallet_count:
                        opening_age_days = (rec.date_from - lifecycle_start_date).days + 1
                    closing_age_end_date = rec.date_to if closing_pallet_count else consumed_datetime.date() if consumed_datetime else False
                    if closing_age_end_date:
                        closing_age_days = (closing_age_end_date - lifecycle_start_date).days + 1
                        closing_age_days_list.append(closing_age_days)
                    lifecycle_end_date = consumed_datetime.date() if consumed_datetime else rec.date_to
                    period_start_date = max(lifecycle_start_date, rec.date_from)
                    period_end_date = min(lifecycle_end_date, rec.date_to)
                    if period_start_date <= period_end_date:
                        period_stock_days = (period_end_date - period_start_date).days + 1

                detail_data_map = {}
                template_ids = set()
                missing_lot = False
                negative_stock = False
                for quantity_key, period_data in product_lot_period_map.items():
                    product_id, lot_id = quantity_key
                    on_hand_quantity = product_lot_quantity_map[quantity_key]
                    if on_hand_quantity < -0.000001:
                        negative_stock = True
                    if not any(abs(period_data[field_name]) > 0.000001 for field_name in ("opening_quantity", "inbound_quantity", "outbound_quantity")) and abs(on_hand_quantity) <= 0.000001:
                        continue
                    product = product_map[product_id]
                    product_template = product.product_tmpl_id
                    lot = lot_map.get(lot_id)
                    move_lot_name = lot.name if lot else ""
                    if not lot:
                        missing_lot = True
                    template_ids.add(product_template.id)
                    if rec.product_template_id and product_template != rec.product_template_id:
                        continue
                    if lot_filter and lot_filter not in move_lot_name.lower():
                        continue
                    detail_key = (product_template.id, lot_id)
                    detail_data = detail_data_map.setdefault(detail_key, {
                        "product_template": product_template,
                        "lot": lot,
                        "variant_data": [],
                    })
                    detail_data["variant_data"].append({
                        "product": product,
                        "opening_quantity": period_data["opening_quantity"],
                        "inbound_quantity": period_data["inbound_quantity"],
                        "outbound_quantity": period_data["outbound_quantity"],
                        "on_hand_quantity": on_hand_quantity,
                        "reserved_quantity": current_quant_map[(package_id, product_id, lot_id)],
                    })

                anomaly_messages = []
                if len(template_ids) > 1:
                    anomaly_messages.append(_("Mixed product templates"))
                if missing_lot:
                    anomaly_messages.append(_("Missing lot"))
                if negative_stock:
                    anomaly_messages.append(_("Negative stock"))
                if lifecycle_count > 1:
                    anomaly_messages.append(_("Repeated package lifecycle"))

                first_inbound_order = lifecycle_start_move_line.picking_id.inbound_order_id if lifecycle_start_move_line else False
                first_inbound_picking = lifecycle_start_move_line.picking_id if lifecycle_start_move_line else False
                inbound_order_names = []
                outbound_order_names = []
                inbound_picking_names = []
                outbound_picking_names = []
                picking_state_map = defaultdict(int)
                operation_data_list = []
                for package_event in package_events:
                    move_line = package_event["move_line"]
                    picking = move_line.picking_id
                    outbound_product = outbound_product_model.browse(move_line.move_id.outbound_order_product_id)
                    outbound_order = picking.outbound_order_id or outbound_product.outbound_order_id
                    if package_event["direction"] == "inbound":
                        if picking.inbound_order_id:
                            inbound_order_names.append(picking.inbound_order_id.billno or picking.inbound_order_id.reference or str(picking.inbound_order_id.id))
                        if picking:
                            inbound_picking_names.append(picking.name)
                    elif package_event["direction"] == "outbound":
                        if outbound_order:
                            outbound_order_names.append(outbound_order.billno or outbound_order.reference or str(outbound_order.id))
                        if picking:
                            outbound_picking_names.append(picking.name)
                    if picking:
                        picking_state_map[picking.state] += 1
                    if package_event["date"].date() >= rec.date_from:
                        operation_data_list.append({
                            "move_line": move_line,
                            "direction": package_event["direction"],
                            "is_done": True,
                        })
                for pending_operation in pending_operation_map[package_id]:
                    move_line = pending_operation["move_line"]
                    picking = move_line.picking_id
                    outbound_product = outbound_product_model.browse(move_line.move_id.outbound_order_product_id)
                    outbound_order = picking.outbound_order_id or outbound_product.outbound_order_id
                    if pending_operation["direction"] == "inbound":
                        if picking.inbound_order_id:
                            inbound_order_names.append(picking.inbound_order_id.billno or picking.inbound_order_id.reference or str(picking.inbound_order_id.id))
                        if picking:
                            inbound_picking_names.append(picking.name)
                    elif pending_operation["direction"] == "outbound":
                        if outbound_order:
                            outbound_order_names.append(outbound_order.billno or outbound_order.reference or str(outbound_order.id))
                        if picking:
                            outbound_picking_names.append(picking.name)
                    if picking:
                        picking_state_map[picking.state] += 1
                    operation_data_list.append({
                        "move_line": move_line,
                        "direction": pending_operation["direction"],
                        "is_done": False,
                    })

                stock_values_list = []
                for detail_data in detail_data_map.values():
                    variant_data = detail_data["variant_data"]
                    uom_ids = {variant["product"].uom_id.id for variant in variant_data}
                    same_uom = len(uom_ids) == 1
                    quantity_summary = []
                    variant_summary = []
                    opening_quantity = 0.0
                    inbound_quantity = 0.0
                    outbound_quantity = 0.0
                    on_hand_quantity = 0.0
                    reserved_quantity = 0.0
                    available_quantity = 0.0
                    uom_id = False
                    has_on_hand_quantity = False
                    has_outbound_quantity = False
                    for variant in variant_data:
                        product = variant["product"]
                        variant_name = product.display_name
                        quantity_summary.append(
                            _("%(variant)s: opening %(opening)s %(uom)s, inbound %(inbound)s %(uom)s, outbound %(outbound)s %(uom)s, closing %(on_hand)s %(uom)s, reserved %(reserved)s %(uom)s, available %(available)s %(uom)s")
                            % {
                                "variant": variant_name,
                                "opening": variant["opening_quantity"],
                                "inbound": variant["inbound_quantity"],
                                "outbound": variant["outbound_quantity"],
                                "on_hand": variant["on_hand_quantity"],
                                "reserved": variant["reserved_quantity"],
                                "available": variant["on_hand_quantity"] - variant["reserved_quantity"],
                                "uom": product.uom_id.name,
                            }
                        )
                        variant_summary.append(_("%(variant)s: %(quantity)s %(uom)s") % {
                            "variant": variant_name,
                            "quantity": variant["on_hand_quantity"],
                            "uom": product.uom_id.name,
                        })
                        has_on_hand_quantity = has_on_hand_quantity or variant["on_hand_quantity"] > 0.000001
                        has_outbound_quantity = has_outbound_quantity or variant["outbound_quantity"] > 0.000001
                        if same_uom:
                            opening_quantity += variant["opening_quantity"]
                            inbound_quantity += variant["inbound_quantity"]
                            outbound_quantity += variant["outbound_quantity"]
                            on_hand_quantity += variant["on_hand_quantity"]
                            reserved_quantity += variant["reserved_quantity"]
                            uom_id = product.uom_id.id
                    if same_uom:
                        available_quantity = on_hand_quantity - reserved_quantity
                    if has_on_hand_quantity and has_outbound_quantity:
                        stock_state = "partial_outbound"
                    elif has_on_hand_quantity:
                        stock_state = "in_stock"
                    elif has_outbound_quantity:
                        stock_state = "fully_outbound"
                    else:
                        stock_state = "out_of_stock"
                    stock_values_list.append({
                        "product_template_id": detail_data["product_template"].id,
                        "lot_id": detail_data["lot"].id if detail_data["lot"] else False,
                        "stock_state": stock_state,
                        "opening_quantity": opening_quantity,
                        "inbound_quantity": inbound_quantity,
                        "outbound_quantity": outbound_quantity,
                        "on_hand_quantity": on_hand_quantity,
                        "reserved_quantity": reserved_quantity,
                        "available_quantity": available_quantity,
                        "uom_id": uom_id,
                        "quantity_summary": "\n".join(quantity_summary),
                        "variant_summary": "\n".join(variant_summary),
                        "reservation_note": "" if rec.date_to == fields.Date.context_today(rec) else _("Reserved quantity is available for the current date only."),
                    })

                operation_values_list = []
                for operation_data in operation_data_list:
                    move_line = operation_data["move_line"]
                    picking = move_line.picking_id
                    outbound_product = outbound_product_model.browse(move_line.move_id.outbound_order_product_id)
                    outbound_order = picking.outbound_order_id or outbound_product.outbound_order_id
                    operation_values_list.append({
                        "direction": operation_data["direction"],
                        "inbound_order_id": picking.inbound_order_id.id if picking.inbound_order_id else False,
                        "outbound_order_id": outbound_order.id if outbound_order else False,
                        "picking_id": picking.id,
                        "picking_state": picking.state if picking else "draft",
                        "product_id": move_line.product_id.id,
                        "lot_id": move_line.lot_id.id,
                        "planned_quantity": move_line.move_id.product_uom_qty,
                        "reserved_quantity": move_line.quantity if not operation_data["is_done"] and picking.state == "assigned" else 0.0,
                        "done_quantity": move_line.quantity if operation_data["is_done"] else 0.0,
                        "uom_id": move_line.product_uom_id.id,
                        "operation_datetime": move_line.date,
                    })

                state_summary = ", ".join(
                    "%s: %s" % (state, count)
                    for state, count in sorted(picking_state_map.items())
                )
                line_data_map[package_id] = {
                    "values": {
                        "package_id": package_id,
                        "pallet_no": package_data["pallet_no"],
                        "warehouse_id": package_data["warehouse"].id if package_data["warehouse"] else False,
                        "owner_id": package_data["owner"].id if package_data["owner"] else False,
                        "lifecycle_state": "active" if closing_pallet_count else "consumed",
                        "lifecycle_start_datetime": lifecycle_start_datetime,
                        "consumed_datetime": consumed_datetime if not closing_pallet_count else False,
                        "first_inbound_order_id": first_inbound_order.id if first_inbound_order else False,
                        "first_inbound_picking_id": first_inbound_picking.id if first_inbound_picking else False,
                        "inbound_order_names": ", ".join(dict.fromkeys(inbound_order_names)),
                        "outbound_order_names": ", ".join(dict.fromkeys(outbound_order_names)),
                        "inbound_picking_names": ", ".join(dict.fromkeys(inbound_picking_names)),
                        "outbound_picking_names": ", ".join(dict.fromkeys(outbound_picking_names)),
                        "picking_state_summary": state_summary,
                        "opening_pallet_count": opening_pallet_count,
                        "inbound_pallet_count": inbound_pallet_count,
                        "outbound_pallet_count": 1 if outbound_cleared_in_period and not closing_pallet_count else 0,
                        "closing_pallet_count": closing_pallet_count,
                        "opening_age_days": opening_age_days,
                        "closing_age_days": closing_age_days,
                        "period_stock_days": period_stock_days,
                        "anomaly_message": "; ".join(anomaly_messages),
                    },
                    "stock_values_list": stock_values_list,
                    "operation_values_list": operation_values_list,
                }

            rec.line_ids.unlink()
            report_lines = report_line_model.create([dict(data["values"], report_id=rec.id) for data in line_data_map.values()]) if line_data_map else report_line_model
            report_line_map = {line.package_id.id: line for line in report_lines}
            stock_values_list = []
            operation_values_list = []
            for package_id, line_data in line_data_map.items():
                report_line = report_line_map[package_id]
                for stock_values in line_data["stock_values_list"]:
                    stock_values["report_line_id"] = report_line.id
                    stock_values_list.append(stock_values)
                for operation_values in line_data["operation_values_list"]:
                    operation_values["report_line_id"] = report_line.id
                    operation_values_list.append(operation_values)
            if stock_values_list:
                stock_line_model.create(stock_values_list)
            if operation_values_list:
                operation_line_model.create(operation_values_list)

            rec.write({
                "state": "done",
                "refreshed_by_id": self.env.user.id,
                "refreshed_datetime": fields.Datetime.now(),
                "average_age_days": sum(closing_age_days_list) / len(closing_age_days_list) if closing_age_days_list else 0.0,
                "maximum_age_days": max(closing_age_days_list) if closing_age_days_list else 0,
                "over_180_pallet_count": len([age_days for age_days in closing_age_days_list if age_days > 180]),
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
                "name": _("Sunrise Pallet Aging Lines"),
                "res_model": "sunrise.stock.report.line",
                "view_mode": "list,form",
                "domain": [("report_id", "=", rec.id)],
                "context": {"create": False, "edit": False},
                "target": "current",
            }
        return action

    def action_export_pallet_summary_excel(self):
        action = False

        for rec in self:
            action = rec.action_export_report_excel("pallet_summary")
        return action

    def action_export_product_stock_excel(self):
        action = False

        for rec in self:
            action = rec.action_export_report_excel("product_stock")
        return action

    def action_export_operation_excel(self):
        action = False

        for rec in self:
            action = rec.action_export_report_excel("operation")
        return action

    def action_export_report_excel(self, export_type):
        report_line_model = self.env["sunrise.stock.report.line"].sudo()
        stock_line_model = self.env["sunrise.stock.report.product.line"].sudo()
        operation_line_model = self.env["sunrise.stock.report.operation.line"].sudo()
        attachment_model = self.env["ir.attachment"]
        action = False

        for rec in self:
            if rec.state != "done":
                raise ValidationError(_("Please refresh the report before exporting."))

            if export_type == "pallet_summary":
                sheet_name = "Pallet Summary"
                file_prefix = "Sunrise_Pallet_Summary"
                headers = ["Package", "Original Pallet", "Lifecycle State", "Lifecycle Start", "Consumed At", "Inbound Orders", "Outbound Orders", "Inbound Pickings", "Outbound Pickings", "Opening Pallets", "Inbound Pallets", "Outbound Pallets", "Closing Pallets", "Opening Age Days", "Closing Age Days", "Period Stock Days", "Anomaly"]
                widths = [28, 22, 16, 20, 20, 24, 24, 24, 24, 14, 14, 15, 14, 16, 16, 17, 24]
                state_label_map = dict(report_line_model._fields["lifecycle_state"].selection)
                report_lines = report_line_model.search([("report_id", "=", rec.id)], order="pallet_no asc, id asc")
                rows = [
                    [
                        line.package_id.name or "",
                        line.pallet_no or "",
                        state_label_map.get(line.lifecycle_state, ""),
                        fields.Datetime.context_timestamp(rec, line.lifecycle_start_datetime).strftime("%Y-%m-%d %H:%M:%S") if line.lifecycle_start_datetime else "",
                        fields.Datetime.context_timestamp(rec, line.consumed_datetime).strftime("%Y-%m-%d %H:%M:%S") if line.consumed_datetime else "",
                        line.inbound_order_names or "",
                        line.outbound_order_names or "",
                        line.inbound_picking_names or "",
                        line.outbound_picking_names or "",
                        line.opening_pallet_count,
                        line.inbound_pallet_count,
                        line.outbound_pallet_count,
                        line.closing_pallet_count,
                        line.opening_age_days,
                        line.closing_age_days,
                        line.period_stock_days,
                        line.anomaly_message or "",
                    ]
                    for line in report_lines
                ]
            elif export_type == "product_stock":
                sheet_name = "Product Lot Stock"
                file_prefix = "Sunrise_Product_Lot_Stock"
                headers = ["Package", "Original Pallet", "Product", "Lot", "Stock State", "Opening Quantity", "Inbound Quantity", "Outbound Quantity", "Closing Quantity", "Reserved Quantity", "Available Quantity", "Unit", "Variant Specifications", "Variant Quantity Details", "Reservation Note"]
                widths = [28, 22, 32, 20, 18, 16, 16, 17, 16, 17, 17, 12, 32, 36, 32]
                state_label_map = dict(stock_line_model._fields["stock_state"].selection)
                stock_lines = stock_line_model.search([("report_line_id.report_id", "=", rec.id)], order="report_line_id, product_template_id, lot_id, id")
                rows = [
                    [
                        line.report_line_id.package_id.name or "",
                        line.report_line_id.pallet_no or "",
                        line.product_template_id.display_name or "",
                        line.lot_id.name or "",
                        state_label_map.get(line.stock_state, ""),
                        line.opening_quantity,
                        line.inbound_quantity,
                        line.outbound_quantity,
                        line.on_hand_quantity,
                        line.reserved_quantity,
                        line.available_quantity,
                        line.uom_id.name or "",
                        line.variant_summary or "",
                        line.quantity_summary or "",
                        line.reservation_note or "",
                    ]
                    for line in stock_lines
                ]
            elif export_type == "operation":
                sheet_name = "Operations"
                file_prefix = "Sunrise_Pallet_Operations"
                headers = ["Package", "Original Pallet", "Direction", "Inbound Order", "Outbound Order", "Picking", "Picking State", "Product Variant", "Lot", "Planned Quantity", "Reserved Quantity", "Done Quantity", "Unit", "Operation Datetime"]
                widths = [28, 22, 16, 22, 22, 22, 16, 32, 20, 17, 17, 16, 12, 21]
                direction_label_map = dict(operation_line_model._fields["direction"].selection)
                state_label_map = dict(operation_line_model._fields["picking_state"].selection)
                operation_lines = operation_line_model.search([("report_line_id.report_id", "=", rec.id)], order="operation_datetime desc, id desc")
                rows = [
                    [
                        line.report_line_id.package_id.name or "",
                        line.report_line_id.pallet_no or "",
                        direction_label_map.get(line.direction, ""),
                        line.inbound_order_id.display_name or "",
                        line.outbound_order_id.display_name or "",
                        line.picking_id.name or "",
                        state_label_map.get(line.picking_state, ""),
                        line.product_id.display_name or "",
                        line.lot_id.name or "",
                        line.planned_quantity,
                        line.reserved_quantity,
                        line.done_quantity,
                        line.uom_id.name or "",
                        fields.Datetime.context_timestamp(rec, line.operation_datetime).strftime("%Y-%m-%d %H:%M:%S") if line.operation_datetime else "",
                    ]
                    for line in operation_lines
                ]
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
            header_row = 5

            worksheet.merge_range(0, 0, 0, len(headers) - 1, "%s - %s" % (sheet_name, rec.name or ""), title_format)
            worksheet.write(2, 0, "Period", label_format)
            worksheet.merge_range(2, 1, 2, 3, "%s to %s" % (rec.date_from or "", rec.date_to or ""), value_format)
            worksheet.write(3, 0, "Warehouse", label_format)
            worksheet.merge_range(3, 1, 3, 3, rec.warehouse_id.display_name or "", value_format)
            worksheet.write(4, 0, "Project", label_format)
            worksheet.merge_range(4, 1, 4, 3, "SUNRISE", value_format)
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
                "name": "%s_%s.xlsx" % (file_prefix, rec.name or rec.id),
                "type": "binary",
                "datas": base64.b64encode(output.read()),
                "res_model": rec._name,
                "res_id": rec.id,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            })
            action = {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % attachment.id, "target": "self"}
        return action


class SunriseStockReportLine(models.Model):
    _name = "sunrise.stock.report.line"
    _description = "Sunrise Pallet Aging Report Line"
    _order = "id desc"

    report_id = fields.Many2one("sunrise.stock.report", string="Report", required=True, ondelete="cascade", index=True, copy=False)
    package_id = fields.Many2one("stock.quant.package", string="Package", readonly=True, index=True, copy=False)
    product_template_id = fields.Many2one("product.template", string="Product", readonly=True, index=True, copy=False)
    pallet_no = fields.Char(string="Original Pallet No", readonly=True, index=True, copy=False)
    warehouse_id = fields.Many2one("stock.warehouse", string="Warehouse", readonly=True, index=True, copy=False)
    owner_id = fields.Many2one("res.partner", string="Owner", readonly=True, index=True, copy=False)
    lifecycle_state = fields.Selection([("active", "Active"), ("consumed", "Consumed"), ("closed", "Closed")], string="Lifecycle State", readonly=True, index=True, copy=False)
    lifecycle_start_datetime = fields.Datetime(string="Lifecycle Start", readonly=True, copy=False, index=True, oldname="first_inbound_datetime")
    consumed_datetime = fields.Datetime(string="Consumed At", readonly=True, copy=False, index=True)
    first_inbound_order_id = fields.Many2one("world.depot.inbound.order", string="First Inbound Order", readonly=True, copy=False)
    first_inbound_picking_id = fields.Many2one("stock.picking", string="First Inbound Picking", readonly=True, copy=False)
    inbound_order_names = fields.Char(string="Inbound Orders", readonly=True, copy=False)
    outbound_order_names = fields.Char(string="Outbound Orders", readonly=True, copy=False)
    inbound_picking_names = fields.Char(string="Inbound Pickings", readonly=True, copy=False)
    outbound_picking_names = fields.Char(string="Outbound Pickings", readonly=True, copy=False)
    picking_state_summary = fields.Char(string="Picking State Summary", readonly=True, copy=False)
    opening_pallet_count = fields.Integer(string="Opening Pallets", readonly=True, copy=False)
    inbound_pallet_count = fields.Integer(string="Inbound Pallets", readonly=True, copy=False)
    outbound_pallet_count = fields.Integer(string="Outbound Pallets", readonly=True, copy=False)
    closing_pallet_count = fields.Integer(string="Closing Pallets", readonly=True, copy=False)
    opening_age_days = fields.Integer(string="Opening Age Days", readonly=True, copy=False)
    closing_age_days = fields.Integer(string="Closing Age Days", readonly=True, copy=False)
    period_stock_days = fields.Integer(string="Period Stock Days", readonly=True, copy=False)
    anomaly_message = fields.Char(string="Anomaly", readonly=True, copy=False)
    stock_line_ids = fields.One2many("sunrise.stock.report.product.line", "report_line_id", string="Stock Lines", readonly=True, copy=False)
    operation_line_ids = fields.One2many("sunrise.stock.report.operation.line", "report_line_id", string="Operation Lines", readonly=True, copy=False)

    def action_view_stock_lines(self):
        action = False

        for rec in self:
            action = {
                "type": "ir.actions.act_window",
                "name": _("Pallet Stock Details"),
                "res_model": "sunrise.stock.report.product.line",
                "view_mode": "list,form",
                "domain": [("report_line_id", "=", rec.id)],
                "context": {"create": False, "edit": False},
                "target": "current",
            }
        return action

    def action_view_operation_lines(self):
        action = False

        for rec in self:
            action = {
                "type": "ir.actions.act_window",
                "name": _("Pallet Operations"),
                "res_model": "sunrise.stock.report.operation.line",
                "view_mode": "list,form",
                "domain": [("report_line_id", "=", rec.id)],
                "context": {"create": False, "edit": False},
                "target": "current",
            }
        return action


class SunriseStockReportProductLine(models.Model):
    _name = "sunrise.stock.report.product.line"
    _description = "Sunrise Pallet Aging Stock Line"
    _order = "id desc"

    report_line_id = fields.Many2one("sunrise.stock.report.line", string="Pallet Summary", required=True, ondelete="cascade", index=True, copy=False)
    product_template_id = fields.Many2one("product.template", string="Product", required=True, readonly=True, index=True, copy=False)
    lot_id = fields.Many2one("stock.lot", string="Lot", readonly=True, index=True, copy=False)
    lot_name = fields.Char(related="lot_id.name", string="Lot No", readonly=True)
    stock_state = fields.Selection([("in_stock", "In Stock"), ("partial_outbound", "Partially Outbound"), ("fully_outbound", "Fully Outbound"), ("out_of_stock", "Out of Stock")], string="Stock State", readonly=True, copy=False, index=True)
    opening_quantity = fields.Float(string="Opening Quantity", readonly=True, copy=False)
    inbound_quantity = fields.Float(string="Inbound Quantity", readonly=True, copy=False)
    outbound_quantity = fields.Float(string="Outbound Quantity", readonly=True, copy=False)
    on_hand_quantity = fields.Float(string="Closing Quantity", readonly=True, copy=False)
    reserved_quantity = fields.Float(string="Current Reserved Quantity", readonly=True, copy=False)
    available_quantity = fields.Float(string="Available Quantity", readonly=True, copy=False)
    uom_id = fields.Many2one("uom.uom", string="Unit", readonly=True, copy=False)
    quantity_summary = fields.Text(string="Variant Quantity Details", readonly=True, copy=False)
    variant_summary = fields.Text(string="Variant Specifications", readonly=True, copy=False)
    reservation_note = fields.Char(string="Reservation Note", readonly=True, copy=False)


class SunriseStockReportOperationLine(models.Model):
    _name = "sunrise.stock.report.operation.line"
    _description = "Sunrise Pallet Aging Operation Line"
    _order = "operation_datetime desc, id desc"

    report_line_id = fields.Many2one("sunrise.stock.report.line", string="Pallet Summary", required=True, ondelete="cascade", index=True, copy=False)
    direction = fields.Selection([("inbound", "Inbound"), ("outbound", "Outbound"), ("internal", "Internal Transfer"), ("adjustment", "Adjustment")], string="Direction", required=True, readonly=True, index=True, copy=False)
    inbound_order_id = fields.Many2one("world.depot.inbound.order", string="Inbound Order", readonly=True, index=True, copy=False)
    outbound_order_id = fields.Many2one("world.depot.outbound.order", string="Outbound Order", readonly=True, index=True, copy=False)
    picking_id = fields.Many2one("stock.picking", string="Picking", readonly=True, index=True, copy=False)
    picking_state = fields.Selection([("draft", "Draft"), ("waiting", "Waiting"), ("confirmed", "Ready"), ("assigned", "Assigned"), ("done", "Done"), ("cancel", "Cancelled")], string="Picking State", readonly=True, index=True, copy=False)
    product_id = fields.Many2one("product.product", string="Product Variant", readonly=True, index=True, copy=False)
    lot_id = fields.Many2one("stock.lot", string="Lot", readonly=True, index=True, copy=False)
    planned_quantity = fields.Float(string="Planned Quantity", readonly=True, copy=False)
    reserved_quantity = fields.Float(string="Reserved Quantity", readonly=True, copy=False)
    done_quantity = fields.Float(string="Done Quantity", readonly=True, copy=False)
    uom_id = fields.Many2one("uom.uom", string="Unit", readonly=True, copy=False)
    operation_datetime = fields.Datetime(string="Operation Datetime", readonly=True, index=True, copy=False)
