# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import datetime, time

from odoo import api, fields, models

from .utils import (
    portal_format_datetime,
    portal_location_is_allowed,
    portal_owner_partner,
    portal_product_code,
)


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    @api.model
    def get_portal_stock_movement_history(self, filters=None):
        filters = filters or {}
        location_id = filters.get("location_id")
        date_from_value = filters.get("date_from")
        date_to_value = filters.get("date_to")
        if not location_id or not date_from_value or not date_to_value or not portal_location_is_allowed(self.env, location_id):
            return []
        try:
            date_from = fields.Date.to_date(date_from_value)
            date_to = fields.Date.to_date(date_to_value)
        except (TypeError, ValueError):
            return []
        owner = portal_owner_partner(self.env)
        if not owner:
            return []
        location_id = int(location_id)
        date_from_datetime = datetime.combine(date_from, time.min)
        date_to_datetime = datetime.combine(date_to, time.max)
        location_ids = set(self.env["stock.location"].sudo().search([
            ("id", "child_of", location_id),
        ]).ids)
        if not location_ids:
            return []

        move_lines = self.sudo().search([
            ("state", "=", "done"),
            ("owner_id", "=", owner.id),
            ("date", "<=", date_to_datetime),
            "|", ("location_id", "child_of", location_id), ("location_dest_id", "child_of", location_id),
        ], order="date asc, id asc")
        package_event_map = defaultdict(list)
        for move_line in move_lines:
            source_inside = move_line.location_id.id in location_ids
            destination_inside = move_line.location_dest_id.id in location_ids
            if source_inside == destination_inside:
                continue
            if destination_inside:
                package = move_line.result_package_id or move_line.package_id
                direction = "inbound"
                signed_quantity = move_line.quantity
                inside_location = move_line.location_dest_id
            else:
                package = move_line.package_id or move_line.result_package_id
                direction = "outbound"
                signed_quantity = -move_line.quantity
                inside_location = move_line.location_id
            if not signed_quantity:
                continue
            is_loose = not package
            lot_key = move_line.lot_id.id or move_line.lot_name or False
            package_key = package.id if package else ("loose", move_line.product_id.id, lot_key, move_line.product_uom_id.id)
            package_event_map[package_key].append({
                "package": package,
                "is_loose": is_loose,
                "move_line": move_line,
                "direction": direction,
                "signed_quantity": signed_quantity,
                "inside_location": inside_location,
            })

        outbound_product_env = self.env["world.depot.outbound.order.product"].sudo()
        rows = []
        package_ids = []
        for package_id, package_events in package_event_map.items():
            package = package_events[0]["package"]
            is_loose = package_events[0]["is_loose"]
            first_move_line = package_events[0]["move_line"]
            product_data_map = {}
            quantity_map = defaultdict(float)
            operation_line_ids = []
            inbound_order_names = []
            outbound_order_names = []
            inbound_picking_names = []
            outbound_picking_names = []
            picking_state_map = defaultdict(int)
            lot_names = []
            lot_name_set = set()
            opening_pallet_count = 0
            inbound_pallet_count = 0
            outbound_pallet_count = 0
            lifecycle_start_datetime = False
            consumed_datetime = False
            closing_location = False
            opening_set = False
            opening_has_stock = False
            period_has_event = False
            period_interval_start = False
            period_intervals = []
            pallet_no = package.original_pallet_no or "" if package else ""

            for package_event in package_events:
                move_line = package_event["move_line"]
                event_datetime = move_line.date
                product = move_line.product_id
                lot = move_line.lot_id
                uom = move_line.product_uom_id
                product_key = (product.id, lot.id, uom.id)
                product_data = product_data_map.setdefault(product_key, {
                    "product_id": product.id,
                    "product_name": product.display_name or product.name or "",
                    "product_code": portal_product_code(product),
                    "lot_id": lot.id if lot else False,
                    "lot_name": lot.name if lot else move_line.lot_name or "",
                    "uom_name": uom.name or "",
                    "opening_quantity": 0.0,
                    "inbound_quantity": 0.0,
                    "outbound_quantity": 0.0,
                    "on_hand_quantity": 0.0,
                    "closing_location_name": "",
                })
                if product_data["lot_name"] and product_data["lot_name"] not in lot_name_set:
                    lot_name_set.add(product_data["lot_name"])
                    lot_names.append(product_data["lot_name"])
                if not is_loose and not pallet_no and move_line.inbound_order_product_pallet_id:
                    pallet_no = move_line.inbound_order_product_pallet_id.inbound_order_product_id.pallet_no or ""

                if not opening_set and event_datetime >= date_from_datetime:
                    for product_key_value, quantity in quantity_map.items():
                        if product_key_value in product_data_map:
                            product_data_map[product_key_value]["opening_quantity"] = quantity
                    opening_has_stock = any(quantity > 0.000001 for quantity in quantity_map.values())
                    opening_pallet_count = 1 if not is_loose and opening_has_stock else 0
                    opening_set = True
                    if opening_has_stock:
                        period_interval_start = date_from

                before_active = any(quantity > 0.000001 for quantity in quantity_map.values())
                quantity_map[product_key] += package_event["signed_quantity"]
                product_data["closing_location_name"] = package_event["inside_location"].complete_name or package_event["inside_location"].display_name or ""
                closing_location = package_event["inside_location"]
                after_active = any(quantity > 0.000001 for quantity in quantity_map.values())
                if not before_active and after_active:
                    lifecycle_start_datetime = event_datetime
                    consumed_datetime = False
                elif before_active and not after_active:
                    consumed_datetime = event_datetime

                if event_datetime < date_from_datetime:
                    continue
                period_has_event = True
                if package_event["direction"] == "inbound":
                    product_data["inbound_quantity"] += move_line.quantity
                    if not before_active and after_active:
                        if not is_loose:
                            inbound_pallet_count += 1
                        period_interval_start = event_datetime.date()
                else:
                    product_data["outbound_quantity"] += move_line.quantity
                    if before_active and not after_active:
                        if not is_loose:
                            outbound_pallet_count += 1
                        if period_interval_start:
                            period_intervals.append((period_interval_start, event_datetime.date()))
                            period_interval_start = False

                picking = move_line.picking_id
                inbound_order = picking.inbound_order_id if picking else False
                outbound_product = outbound_product_env.browse(move_line.move_id.outbound_order_product_id)
                outbound_order = picking.outbound_order_id if picking else False
                outbound_order = outbound_order or outbound_product.outbound_order_id
                if package_event["direction"] == "inbound":
                    if inbound_order:
                        inbound_order_names.append(inbound_order.billno or inbound_order.reference or str(inbound_order.id))
                    if picking:
                        inbound_picking_names.append(picking.name)
                else:
                    if outbound_order:
                        outbound_order_names.append(outbound_order.billno or outbound_order.reference or str(outbound_order.id))
                    if picking:
                        outbound_picking_names.append(picking.name)
                if picking:
                    picking_state_map[picking.state] += 1
                operation_line_ids.append({
                    "direction": package_event["direction"],
                    "inbound_order_id": inbound_order.id if inbound_order else False,
                    "inbound_order_name": inbound_order.display_name if inbound_order else "",
                    "outbound_order_id": outbound_order.id if outbound_order else False,
                    "outbound_order_name": outbound_order.display_name if outbound_order else "",
                    "picking_id": picking.id if picking else False,
                    "picking_name": picking.name if picking else "",
                    "picking_state": picking.state if picking else "",
                    "product_id": product.id,
                    "product_name": product.display_name or product.name or "",
                    "product_code": portal_product_code(product),
                    "lot_id": lot.id if lot else False,
                    "lot_name": lot.name if lot else move_line.lot_name or "",
                    "planned_quantity": move_line.move_id.product_uom_qty,
                    "reserved_quantity": 0.0,
                    "done_quantity": move_line.quantity,
                    "uom_name": uom.name or "",
                    "operation_datetime": portal_format_datetime(event_datetime),
                    "source_location_name": move_line.location_id.complete_name or move_line.location_id.display_name or "",
                    "destination_location_name": move_line.location_dest_id.complete_name or move_line.location_dest_id.display_name or "",
                })

            if not opening_set:
                for product_key_value, quantity in quantity_map.items():
                    if product_key_value in product_data_map:
                        product_data_map[product_key_value]["opening_quantity"] = quantity
                opening_has_stock = any(quantity > 0.000001 for quantity in quantity_map.values())
                opening_pallet_count = 1 if not is_loose and opening_has_stock else 0
                if opening_has_stock:
                    period_interval_start = date_from
            if not opening_has_stock and not period_has_event:
                continue
            if any(quantity > 0.000001 for quantity in quantity_map.values()) and period_interval_start:
                period_intervals.append((period_interval_start, date_to))
            merged_intervals = []
            for interval_start, interval_end in period_intervals:
                if not merged_intervals or interval_start > merged_intervals[-1][1]:
                    merged_intervals.append([interval_start, interval_end])
                elif interval_end > merged_intervals[-1][1]:
                    merged_intervals[-1][1] = interval_end
            period_stock_days = sum((interval_end - interval_start).days + 1 for interval_start, interval_end in merged_intervals)
            closing_has_stock = any(quantity > 0.000001 for quantity in quantity_map.values())
            closing_pallet_count = 1 if not is_loose and closing_has_stock else 0
            closing_age_end = date_to if closing_has_stock else consumed_datetime.date() if consumed_datetime else False
            closing_age_days = (closing_age_end - lifecycle_start_datetime.date()).days + 1 if lifecycle_start_datetime and closing_age_end else 0

            stock_line_ids = []
            summary_map = {
                "opening_product_summary": defaultdict(float),
                "inbound_product_summary": defaultdict(float),
                "outbound_product_summary": defaultdict(float),
                "closing_product_summary": defaultdict(float),
            }
            for product_key, product_data in product_data_map.items():
                product_data["on_hand_quantity"] = quantity_map[product_key]
                if not any(abs(product_data[field_name]) > 0.000001 for field_name in ("opening_quantity", "inbound_quantity", "outbound_quantity", "on_hand_quantity")):
                    continue
                product_data["reserved_quantity"] = 0.0
                product_data["available_quantity"] = product_data["on_hand_quantity"]
                product_data["reservation_note"] = "Reserved quantity is available for the current date only." if date_to != fields.Date.context_today(self) else ""
                stock_line_ids.append(product_data)
                summary_map["opening_product_summary"][product_data["uom_name"]] += product_data["opening_quantity"]
                summary_map["inbound_product_summary"][product_data["uom_name"]] += product_data["inbound_quantity"]
                summary_map["outbound_product_summary"][product_data["uom_name"]] += product_data["outbound_quantity"]
                summary_map["closing_product_summary"][product_data["uom_name"]] += product_data["on_hand_quantity"]
            if not stock_line_ids and not operation_line_ids:
                continue
            row = {
                "row_type": "loose" if is_loose else "package",
                "package_id": package.id if package else False,
                "package_name": "No Pallet" if is_loose else package.name or "",
                "pallet_no": pallet_no,
                "product_id": first_move_line.product_id.id if is_loose else False,
                "product_name": (first_move_line.product_id.display_name or first_move_line.product_id.name or "") if is_loose else "",
                "lot_name": (first_move_line.lot_id.name or first_move_line.lot_name or "") if is_loose else "",
                "uom_name": first_move_line.product_uom_id.name or "" if is_loose else "",
                "lot_summary": ", ".join(lot_names),
                "closing_location_name": (closing_location.complete_name or closing_location.display_name or "") if closing_location else "",
                "lifecycle_state": "active" if closing_has_stock else "consumed",
                "lifecycle_start_datetime": portal_format_datetime(lifecycle_start_datetime),
                "consumed_datetime": portal_format_datetime(consumed_datetime),
                "inbound_order_names": ", ".join(dict.fromkeys(inbound_order_names)),
                "outbound_order_names": ", ".join(dict.fromkeys(outbound_order_names)),
                "inbound_picking_names": ", ".join(dict.fromkeys(inbound_picking_names)),
                "outbound_picking_names": ", ".join(dict.fromkeys(outbound_picking_names)),
                "picking_state_summary": ", ".join("%s: %s" % (state, count) for state, count in sorted(picking_state_map.items())),
                "opening_pallet_count": opening_pallet_count,
                "inbound_pallet_count": inbound_pallet_count,
                "outbound_pallet_count": outbound_pallet_count,
                "closing_pallet_count": closing_pallet_count,
                "period_stock_days": period_stock_days,
                "closing_age_days": closing_age_days,
                "stock_line_ids": sorted(stock_line_ids, key=lambda line: (line["product_name"], line["lot_name"], line["uom_name"])),
                "operation_line_ids": sorted(operation_line_ids, key=lambda line: line["operation_datetime"], reverse=True),
            }
            for summary_name, summary_by_uom in summary_map.items():
                row[summary_name] = ", ".join(
                    "%s %s" % ("%g" % quantity, uom_name)
                    for uom_name, quantity in summary_by_uom.items()
                    if abs(quantity) > 0.000001
                )
            rows.append(row)
            if package:
                package_ids.append(package.id)

        if date_to == fields.Date.context_today(self) and rows:
            reserved_quantity_map = defaultdict(float)
            quant_domain = [
                ("owner_id", "=", owner.id),
                ("location_id", "child_of", location_id),
                ("reserved_quantity", "!=", 0),
            ]
            quant_domain += ["|", ("package_id", "in", package_ids), ("package_id", "=", False)]
            quants = self.env["stock.quant"].sudo().search(quant_domain)
            for quant in quants:
                reserved_quantity_map[(quant.package_id.id, quant.product_id.id, quant.lot_id.id)] += quant.reserved_quantity
            for row in rows:
                for stock_line in row["stock_line_ids"]:
                    stock_line["reserved_quantity"] = reserved_quantity_map[(row["package_id"], stock_line["product_id"], stock_line["lot_id"])]
                    stock_line["available_quantity"] = stock_line["on_hand_quantity"] - stock_line["reserved_quantity"]
                    stock_line["reservation_note"] = ""
        return sorted(rows, key=lambda row: (row["lifecycle_start_datetime"], row["package_name"]), reverse=True)
