from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.osv import expression


class StockMoveLineHistorySummary(models.Model):
    _inherit = "stock.move.line"

    @api.model
    def get_package_lifecycle_data(self, filters=None):
        filters = filters or {}
        date_from = fields.Date.to_date(filters.get("date_from"))
        date_to = fields.Date.to_date(filters.get("date_to"))
        if not date_from or not date_to:
            raise ValidationError(_("Date From and Date To are required."))
        if date_from > date_to:
            raise ValidationError(_("Date From must not be later than Date To."))
        location_id = filters.get("location_id")
        if location_id:
            try:
                location_id = int(location_id)
            except (TypeError, ValueError):
                raise ValidationError(_("Location must be a valid record."))
        filter_location_ids = filters.get("location_ids")
        if filter_location_ids is not None and not isinstance(filter_location_ids, (list, tuple, set)):
            raise ValidationError(_("Locations must be a valid record list."))
        timezone_name = filters.get("timezone") or self.env.context.get("tz") or self.env.user.tz or "UTC"
        try:
            timezone = pytz.timezone(timezone_name)
        except pytz.UnknownTimeZoneError:
            raise ValidationError(_("Timezone is invalid."))
        date_from_datetime = timezone.localize(datetime.combine(date_from, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        date_to_datetime = timezone.localize(datetime.combine(date_to + timedelta(days=1), time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        move_line_model = self.sudo()
        inbound_domain = [
            ("state", "=", "done"),
            ("date", "<", date_to_datetime),
            ("result_package_id", "!=", False),
            ("picking_id.inbound_order_id", "!=", False),
            ("picking_id.picking_type_id.code", "=", "incoming"),
        ]
        if filters.get("owner_id"):
            inbound_domain.append(("picking_id.inbound_order_id.owner", "=", filters["owner_id"]))
        if "project_ids" in filters:
            if not filters["project_ids"]:
                return {"date_from": date_from, "date_to": date_to, "timezone_name": timezone_name, "package_lifecycle_data": []}
            inbound_domain.append(("picking_id.inbound_order_id.project", "in", filters["project_ids"]))
        elif filters.get("project_id"):
            inbound_domain.append(("picking_id.inbound_order_id.project", "=", filters["project_id"]))
        cprojectid = str(filters.get("cprojectid") or "").strip()
        if cprojectid:
            inbound_pallets = self.env["world.depot.inbound.order.products.pallet"].sudo().search([("cprojectid", "ilike", cprojectid)])
            inbound_order_ids = inbound_pallets.mapped("inbound_order_product_id.inbound_order_id").ids
            inbound_domain.append(("picking_id.inbound_order_id", "in", inbound_order_ids))
        inbound_move_lines = move_line_model.search(inbound_domain, order="date asc, id asc")
        if not inbound_move_lines:
            return {"date_from": date_from, "date_to": date_to, "timezone_name": timezone_name, "package_lifecycle_data": []}
        selected_segment_map = {}
        selected_package_ids = set()
        for move_line in inbound_move_lines:
            inbound_order = move_line.picking_id.inbound_order_id
            package = move_line.result_package_id
            segment_key = (inbound_order.id, package.id)
            segment = selected_segment_map.setdefault(segment_key, {
                "inbound_order_id": inbound_order.id,
                "inbound_order_name": inbound_order.display_name,
                "first_inbound_datetime": move_line.date,
                "cproject_ids": set(),
                "batch_names": set(),
                "is_selected": True,
            })
            selected_package_ids.add(package.id)
            if move_line.date < segment["first_inbound_datetime"]:
                segment["first_inbound_datetime"] = move_line.date
            pallet_detail = move_line.inbound_order_product_pallet_id
            if pallet_detail and pallet_detail.cprojectid:
                segment["cproject_ids"].add(pallet_detail.cprojectid)
            batch_name = (pallet_detail.lot_name if pallet_detail else "") or move_line.lot_id.name or move_line.lot_name or ""
            if batch_name:
                segment["batch_names"].add(batch_name)
        move_line_domain = [
            ("state", "=", "done"),
            ("date", "<", date_to_datetime),
            "|",
            ("package_id", "in", list(selected_package_ids)),
            ("result_package_id", "in", list(selected_package_ids)),
        ]
        move_lines = move_line_model.search(move_line_domain, order="date asc, id asc")
        location_model = self.env["stock.location"].sudo()
        location_ids = False
        if location_id:
            location_ids = set(location_model.search([("id", "child_of", location_id)]).ids)
            if not location_ids:
                return {"date_from": date_from, "date_to": date_to, "timezone_name": timezone_name, "package_lifecycle_data": []}
        elif filter_location_ids is not None:
            try:
                location_ids = {int(filter_location_id) for filter_location_id in filter_location_ids}
            except (TypeError, ValueError):
                raise ValidationError(_("Locations must be a valid record list."))
            if not location_ids:
                return {"date_from": date_from, "date_to": date_to, "timezone_name": timezone_name, "package_lifecycle_data": []}
        package_segment_map = defaultdict(dict)
        for (inbound_order_id, package_id), selected_segment in selected_segment_map.items():
            package_segment_map[package_id][inbound_order_id] = dict(selected_segment, cproject_ids=set(selected_segment["cproject_ids"]), batch_names=set(selected_segment["batch_names"]))
        package_event_map = defaultdict(list)
        for move_line in move_lines:
            source_inside = move_line.location_id.id in location_ids if location_ids is not False else move_line.location_id.usage == "internal"
            destination_inside = move_line.location_dest_id.id in location_ids if location_ids is not False else move_line.location_dest_id.usage == "internal"
            package = move_line.result_package_id
            inbound_order = move_line.picking_id.inbound_order_id
            if package.id in selected_package_ids and inbound_order and move_line.picking_id.picking_type_id.code == "incoming" and move_line.location_id.usage != "internal" and move_line.location_dest_id.usage == "internal":
                segment = package_segment_map[package.id].setdefault(inbound_order.id, {
                    "inbound_order_id": inbound_order.id,
                    "inbound_order_name": inbound_order.display_name,
                    "first_inbound_datetime": move_line.date,
                    "cproject_ids": set(),
                    "batch_names": set(),
                    "is_selected": False,
                })
                if move_line.date < segment["first_inbound_datetime"]:
                    segment["first_inbound_datetime"] = move_line.date
            if location_ids is not False and not source_inside and not destination_inside:
                continue
            source_package_id = move_line.package_id.id
            destination_package_id = move_line.result_package_id.id or source_package_id
            package_quantity_map = defaultdict(float)
            touched_package_ids = set()
            if source_package_id in selected_package_ids:
                touched_package_ids.add(source_package_id)
                if source_inside:
                    package_quantity_map[source_package_id] -= move_line.quantity
            if destination_package_id in selected_package_ids:
                touched_package_ids.add(destination_package_id)
                if destination_inside:
                    package_quantity_map[destination_package_id] += move_line.quantity
            for package_id in touched_package_ids:
                if source_inside and not destination_inside:
                    direction = "outbound"
                elif destination_inside and not source_inside:
                    direction = "inbound"
                else:
                    direction = "internal"
                package_event_map[package_id].append({
                    "move_line_id": move_line.id,
                    "event_datetime": move_line.date,
                    "event_date": fields.Datetime.context_timestamp(self.with_context(tz=timezone_name), move_line.date).date(),
                    "product_id": move_line.product_id.id,
                    "lot_id": move_line.lot_id.id,
                    "quantity": package_quantity_map[package_id],
                    "move_quantity": move_line.quantity,
                    "direction": direction,
                    "source_location_id": move_line.location_id.id,
                    "source_location_name": move_line.location_id.complete_name or move_line.location_id.display_name or "",
                    "destination_location_id": move_line.location_dest_id.id,
                    "destination_location_name": move_line.location_dest_id.complete_name or move_line.location_dest_id.display_name or "",
                    "source_inside": source_inside,
                    "destination_inside": destination_inside,
                    "is_source_package": source_package_id == package_id,
                    "is_destination_package": destination_package_id == package_id,
                    "picking_id": move_line.picking_id.id,
                    "picking_state": move_line.picking_id.state,
                    "picking_type_code": move_line.picking_id.picking_type_id.code,
                    "is_outbound": source_inside and not destination_inside,
                    "is_actual_outbound": source_inside and move_line.location_dest_id.usage != "internal" and move_line.picking_id.picking_type_id.code == "outgoing",
                })
        package_lifecycle_data = []
        for package_id in selected_package_ids:
            segments = sorted(package_segment_map[package_id].values(), key=lambda segment: (segment["first_inbound_datetime"], segment["inbound_order_id"]))
            if not segments:
                continue
            quantity_map = defaultdict(float)
            segment_index = 0
            current_inbound_order_id = False
            opening_captured = False
            opening_inbound_order_id = False
            opening_active = False
            location_quantity_map = defaultdict(float)
            location_last_sequence_map = {}
            location_name_map = {}
            events = []
            for event_sequence, event in enumerate(package_event_map[package_id]):
                if not opening_captured and event["event_datetime"] >= date_from_datetime:
                    opening_inbound_order_id = current_inbound_order_id
                    opening_active = any(quantity > 0.000001 for quantity in quantity_map.values())
                    opening_captured = True
                while segment_index < len(segments) and segments[segment_index]["first_inbound_datetime"] <= event["event_datetime"]:
                    current_inbound_order_id = segments[segment_index]["inbound_order_id"]
                    segment_index += 1
                before_active = any(quantity > 0.000001 for quantity in quantity_map.values())
                quantity_map[(event["product_id"], event["lot_id"])] += event["quantity"]
                after_active = any(quantity > 0.000001 for quantity in quantity_map.values())
                if event["is_source_package"] and event["source_inside"]:
                    location_key = (event["product_id"], event["lot_id"], event["source_location_id"])
                    location_quantity_map[location_key] -= event["move_quantity"]
                    location_last_sequence_map[event["source_location_id"]] = event_sequence * 2
                    location_name_map[event["source_location_id"]] = event["source_location_name"]
                if event["is_destination_package"] and event["destination_inside"]:
                    location_key = (event["product_id"], event["lot_id"], event["destination_location_id"])
                    location_quantity_map[location_key] += event["move_quantity"]
                    location_last_sequence_map[event["destination_location_id"]] = event_sequence * 2 + 1
                    location_name_map[event["destination_location_id"]] = event["destination_location_name"]
                event.update({"inbound_order_id": current_inbound_order_id, "before_active": before_active, "after_active": after_active})
                events.append(event)
            if not opening_captured:
                opening_inbound_order_id = current_inbound_order_id
                opening_active = any(quantity > 0.000001 for quantity in quantity_map.values())
            closing_active = any(quantity > 0.000001 for quantity in quantity_map.values())
            closing_location_quantity_map = defaultdict(float)
            for (_, _, closing_location_id), quantity in location_quantity_map.items():
                closing_location_quantity_map[closing_location_id] += quantity
            closing_location_ids = [closing_location_id for closing_location_id, quantity in closing_location_quantity_map.items() if quantity > 0.000001]
            closing_location_id = max(closing_location_ids, key=lambda closing_location_id: (location_last_sequence_map.get(closing_location_id, -1), closing_location_id)) if closing_location_ids else False
            if not opening_active and not closing_active and not any(event["event_datetime"] >= date_from_datetime for event in events):
                continue
            package_lifecycle_data.append({
                "package_id": package_id,
                "segments": [{
                    "inbound_order_id": segment["inbound_order_id"],
                    "inbound_order_name": segment["inbound_order_name"],
                    "first_inbound_datetime": segment["first_inbound_datetime"],
                    "cproject_ids": sorted(segment["cproject_ids"]),
                    "batch_names": sorted(segment["batch_names"]),
                    "is_selected": segment["is_selected"],
                } for segment in segments],
                "events": events,
                "opening_inbound_order_id": opening_inbound_order_id,
                "opening_active": opening_active,
                "closing_inbound_order_id": current_inbound_order_id,
                "closing_active": closing_active,
                "closing_location_id": closing_location_id,
                "closing_location_name": location_name_map.get(closing_location_id, ""),
            })
        return {"date_from": date_from, "date_to": date_to, "timezone_name": timezone_name, "package_lifecycle_data": package_lifecycle_data}

    @api.model
    def get_package_movement_history(self, filters=None):
        filters = filters or {}
        lifecycle_result = self.get_package_lifecycle_data(filters)
        location_id = filters.get("location_id")
        if not location_id:
            return dict(lifecycle_result, movement_rows=[])
        try:
            location_id = int(location_id)
        except (TypeError, ValueError):
            raise ValidationError(_("Location must be a valid record."))
        project_ids = filters.get("project_ids")
        if not project_ids:
            return dict(lifecycle_result, movement_rows=[])
        date_from = lifecycle_result["date_from"]
        date_to = lifecycle_result["date_to"]
        date_from_datetime = datetime.combine(date_from, time.min)
        date_to_datetime = datetime.combine(date_to, time.max)
        location_ids = set(self.env["stock.location"].sudo().search([("id", "child_of", location_id)]).ids)
        if not location_ids:
            return dict(lifecycle_result, movement_rows=[])

        lifecycle_move_line_ids = {
            event["move_line_id"]
            for package_data in lifecycle_result["package_lifecycle_data"]
            for event in package_data["events"]
        }
        move_line_model = self.sudo()
        lifecycle_move_lines = move_line_model.search([("id", "in", list(lifecycle_move_line_ids))], order="date asc, id asc") if lifecycle_move_line_ids else move_line_model
        move_line_by_id = {move_line.id: move_line for move_line in lifecycle_move_lines}
        package_event_map = defaultdict(list)
        package_model = self.env["stock.quant.package"].sudo()
        for package_data in lifecycle_result["package_lifecycle_data"]:
            package = package_model.browse(package_data["package_id"])
            for lifecycle_event in package_data["events"]:
                if lifecycle_event["direction"] == "internal" or not lifecycle_event["quantity"]:
                    continue
                move_line = move_line_by_id.get(lifecycle_event["move_line_id"])
                if not move_line:
                    continue
                package_event_map[package.id].append({
                    "package": package,
                    "is_loose": False,
                    "move_line": move_line,
                    "direction": lifecycle_event["direction"],
                    "signed_quantity": lifecycle_event["quantity"],
                    "inside_location": move_line.location_dest_id if lifecycle_event["destination_inside"] else move_line.location_id,
                })
        project_move_line_domain = expression.OR([
            [("picking_id.inbound_order_id.project", "in", project_ids)],
            [("picking_id.outbound_order_id.project", "in", project_ids)],
        ])
        loose_move_lines = move_line_model.search(expression.AND([[
            ("state", "=", "done"),
            ("date", "<=", date_to_datetime),
            ("package_id", "=", False),
            ("result_package_id", "=", False),
            "|", ("location_id", "child_of", location_id), ("location_dest_id", "child_of", location_id),
        ], project_move_line_domain]), order="date asc, id asc")
        for move_line in loose_move_lines:
            source_inside = move_line.location_id.id in location_ids
            destination_inside = move_line.location_dest_id.id in location_ids
            if source_inside == destination_inside:
                continue
            if destination_inside:
                direction = "inbound"
                signed_quantity = move_line.quantity
                inside_location = move_line.location_dest_id
            else:
                direction = "outbound"
                signed_quantity = -move_line.quantity
                inside_location = move_line.location_id
            if not signed_quantity:
                continue
            lot_key = move_line.lot_id.id or move_line.lot_name or False
            package_key = ("loose", move_line.product_id.id, lot_key, move_line.product_uom_id.id)
            package_event_map[package_key].append({
                "package": False,
                "is_loose": True,
                "move_line": move_line,
                "direction": direction,
                "signed_quantity": signed_quantity,
                "inside_location": inside_location,
            })

        outbound_product_model = self.env["world.depot.outbound.order.product"].sudo()
        rows = []
        package_ids = []
        for package_events in package_event_map.values():
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
                product_code = product.barcode or product.default_code or ""
                product_display_name = "[%s] %s" % (product_code, product.name or "") if product_code and product.name else product_code or product.name or ""
                product_key = (product.id, lot.id, uom.id)
                product_data = product_data_map.setdefault(product_key, {
                    "product_id": product.id,
                    "product_name": product_display_name,
                    "product_code": product.barcode or product.default_code or "",
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
                outbound_product = outbound_product_model.browse(move_line.move_id.outbound_order_product_id)
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
                    "product_name": product_display_name,
                    "product_code": product.barcode or product.default_code or "",
                    "lot_id": lot.id if lot else False,
                    "lot_name": lot.name if lot else move_line.lot_name or "",
                    "planned_quantity": move_line.move_id.product_uom_qty,
                    "reserved_quantity": 0.0,
                    "done_quantity": move_line.quantity,
                    "uom_name": uom.name or "",
                    "operation_datetime": fields.Datetime.to_string(event_datetime),
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
            loose_product = first_move_line.product_id
            loose_product_code = loose_product.barcode or loose_product.default_code or ""
            loose_product_name = loose_product.name or ""
            if loose_product_code and loose_product_name:
                loose_product_name = "[%s] %s" % (loose_product_code, loose_product_name)
            elif loose_product_code:
                loose_product_name = loose_product_code
            row = {
                "row_type": "loose" if is_loose else "package",
                "package_id": package.id if package else False,
                "package_name": "No Pallet" if is_loose else package.name or "",
                "pallet_no": pallet_no,
                "product_id": first_move_line.product_id.id if is_loose else False,
                "product_name": loose_product_name if is_loose else "",
                "lot_name": (first_move_line.lot_id.name or first_move_line.lot_name or "") if is_loose else "",
                "uom_name": first_move_line.product_uom_id.name or "" if is_loose else "",
                "lot_summary": ", ".join(lot_names),
                "closing_location_name": (closing_location.complete_name or closing_location.display_name or "") if closing_location else "",
                "lifecycle_state": "active" if closing_has_stock else "consumed",
                "lifecycle_start_datetime": fields.Datetime.to_string(lifecycle_start_datetime) if lifecycle_start_datetime else "",
                "consumed_datetime": fields.Datetime.to_string(consumed_datetime) if consumed_datetime else "",
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
            if package_ids:
                quants = self.env["stock.quant"].sudo().search([
                    ("location_id", "child_of", location_id),
                    ("reserved_quantity", "!=", 0),
                    ("package_id", "in", package_ids),
                ])
                for quant in quants:
                    reserved_quantity_map[(quant.package_id.id, quant.product_id.id, quant.lot_id.id)] += quant.reserved_quantity
            for row in rows:
                if not row["package_id"]:
                    continue
                for stock_line in row["stock_line_ids"]:
                    stock_line["reserved_quantity"] = reserved_quantity_map[(row["package_id"], stock_line["product_id"], stock_line["lot_id"])]
                    stock_line["available_quantity"] = stock_line["on_hand_quantity"] - stock_line["reserved_quantity"]
                    stock_line["reservation_note"] = ""
        return dict(lifecycle_result, movement_rows=sorted(rows, key=lambda row: (row["lifecycle_start_datetime"], row["package_name"]), reverse=True))

    @api.model
    def get_inbound_pallet_summary(self, filters=None):
        lifecycle_result = self.get_package_lifecycle_data(filters)
        inbound_data_map = {}
        for package_data in lifecycle_result["package_lifecycle_data"]:
            selected_inbound_order_ids = set()
            segment_map = {segment["inbound_order_id"]: segment for segment in package_data["segments"]}
            for segment in package_data["segments"]:
                if not segment["is_selected"]:
                    continue
                selected_inbound_order_ids.add(segment["inbound_order_id"])
                inbound_data = inbound_data_map.setdefault(segment["inbound_order_id"], {
                    "first_inbound_datetime": segment["first_inbound_datetime"],
                    "inbound_order_id": segment["inbound_order_id"],
                    "inbound_order_name": segment["inbound_order_name"],
                    "cproject_ids": set(),
                    "opening_pallet_count": 0,
                    "inbound_pallet_count": 0,
                    "outbound_pallet_count": 0,
                    "closing_pallet_count": 0,
                    "closing_location_map": defaultdict(int),
                    "outbound_lines": defaultdict(int),
                })
                if segment["first_inbound_datetime"] < inbound_data["first_inbound_datetime"]:
                    inbound_data["first_inbound_datetime"] = segment["first_inbound_datetime"]
                inbound_data["cproject_ids"].update(segment["cproject_ids"])
            if package_data["opening_active"] and package_data["opening_inbound_order_id"] in selected_inbound_order_ids:
                inbound_data_map[package_data["opening_inbound_order_id"]]["opening_pallet_count"] += 1
            if package_data["closing_active"] and package_data["closing_inbound_order_id"] in selected_inbound_order_ids:
                inbound_data = inbound_data_map[package_data["closing_inbound_order_id"]]
                inbound_data["closing_pallet_count"] += 1
                if package_data["closing_location_name"]:
                    inbound_data["closing_location_map"][package_data["closing_location_name"]] += 1
            for event in package_data["events"]:
                if event["event_date"] >= lifecycle_result["date_from"] and event["direction"] == "inbound" and not event["before_active"] and event["after_active"] and event["inbound_order_id"] in selected_inbound_order_ids:
                    inbound_data_map[event["inbound_order_id"]]["inbound_pallet_count"] += 1
                if event["event_date"] >= lifecycle_result["date_from"] and event["is_actual_outbound"] and event["before_active"] and not event["after_active"] and event["inbound_order_id"] in selected_inbound_order_ids:
                    inbound_data = inbound_data_map[event["inbound_order_id"]]
                    inbound_data["outbound_pallet_count"] += 1
                    outbound_segment = segment_map.get(event["inbound_order_id"], {})
                    cproject_ids = ", ".join(outbound_segment.get("cproject_ids", []))
                    batch_names = ", ".join(outbound_segment.get("batch_names", []))
                    inbound_data["outbound_lines"][(event["event_date"], cproject_ids, batch_names)] += 1
        result = []
        for inbound_data in inbound_data_map.values():
            first_inbound_local_datetime = fields.Datetime.context_timestamp(self.with_context(tz=lifecycle_result["timezone_name"]), inbound_data["first_inbound_datetime"])
            closing_pallet_count = inbound_data["closing_pallet_count"]
            remain_period_start_date = max(lifecycle_result["date_from"], first_inbound_local_datetime.date())
            result.append({
                "first_inbound_date": fields.Datetime.to_string(first_inbound_local_datetime),
                "first_inbound_datetime": fields.Datetime.to_string(inbound_data["first_inbound_datetime"]),
                "inbound_order_id": inbound_data["inbound_order_id"],
                "inbound_order_name": inbound_data["inbound_order_name"],
                "cproject_ids": ", ".join(sorted(inbound_data["cproject_ids"])),
                "opening_pallet_count": inbound_data["opening_pallet_count"],
                "inbound_pallet_count": inbound_data["inbound_pallet_count"],
                "outbound_pallet_count": inbound_data["outbound_pallet_count"],
                "closing_pallet_count": closing_pallet_count,
                "closing_location_summary": "; ".join("%s: %s" % (location_name, pallet_count) for location_name, pallet_count in sorted(inbound_data["closing_location_map"].items())),
                "remain_period_age_days": (lifecycle_result["date_to"] - remain_period_start_date).days + 1 if closing_pallet_count else 0,
                "remain_total_age_days": (lifecycle_result["date_to"] - first_inbound_local_datetime.date()).days + 1 if closing_pallet_count else 0,
                "outbound_lines": [{
                    "outbound_date": fields.Date.to_string(outbound_date),
                    "cproject_ids": cproject_ids,
                    "batch_names": batch_names,
                    "pallet_count": pallet_count,
                    "stock_days": (outbound_date - lifecycle_result["date_from"]).days + 1,
                } for (outbound_date, cproject_ids, batch_names), pallet_count in sorted(inbound_data["outbound_lines"].items())],
            })
        return sorted(result, key=lambda inbound_data: (inbound_data["first_inbound_date"], inbound_data["inbound_order_id"]))
