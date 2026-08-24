# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import fields, http
from odoo.addons.portal.controllers.portal import CustomerPortal,pager as portal_pager
from odoo.http import request

from ..models.utils import portal_location_is_allowed
from .portal import MarstekStockPortal


class StockMovementHistoryPortal(CustomerPortal):

    @http.route("/my/world_depot/stock/movement_history_page", type="http", auth="user", website=True)
    def stock_movement_history_page(self, **kw):
        filters = {
            "location_id": str(kw.get("location_id") or "").strip(),
            "location_search": str(kw.get("location_search") or "").strip(),
            "location_name": str(kw.get("location_name") or "").strip(),
            "date_from": str(kw.get("date_from") or "").strip(),
            "date_to": str(kw.get("date_to") or "").strip(),
            "view_mode": str(kw.get('view_mode') or "").strip(),
        }
        values = self._prepare_portal_layout_values()
        values.update({
            "page_name": "marstek_stock_movement_history",
            "marstek_page_title": "Stock Movement History",
            "filters": filters,
            "summary": {},
            "rows": [],
            "pager": {},
            "error": "",
        })
        return request.render("marstek_stock_portal.portal_marstek_stock_history", values)

    @http.route([
        "/my/world_depot/stock/movement_history",
        "/my/world_depot/stock/movement_history/page/<int:page>",
    ], type="http", auth="user", methods=["GET"], website=True)
    def stock_movement_history_portal(self, page=1, **kw):
        filters = {
            "location_id": str(kw.get("location_id") or "").strip(),
            "date_from": str(kw.get("date_from") or "").strip(),
            "date_to": str(kw.get("date_to") or "").strip(),
        }
        # ===== DEMO DATA START - 测试用，测完删除整段（含下面 if True 块） =====
        if True:
            demo_rows = [
                {
                    "row_type": "package", "package_id": 501, "package_name": "PALLET-000501",
                    "pallet_no": "PLT-20260801-01", "product_id": False, "product_name": "",
                    "lot_summary": "LOT-001, LOT-002", "closing_location_name": "SPN/Stock/LOODS06/06",
                    "lifecycle_state": "active", "lifecycle_start_datetime": "2026-07-28 10:30:00",
                    "consumed_datetime": False, "inbound_order_names": "INB-20260728",
                    "outbound_order_names": "OUT-20260810", "inbound_picking_names": "WH/IN/00120",
                    "outbound_picking_names": "WH/OUT/00310", "picking_state_summary": "done: 2",
                    "opening_pallet_count": 1, "opening_product_summary": "100 PCS, 2 BOX",
                    "inbound_pallet_count": 0, "inbound_product_summary": "",
                    "outbound_pallet_count": 0, "outbound_product_summary": "20 PCS",
                    "closing_pallet_count": 1, "closing_product_summary": "80 PCS, 2 BOX",
                    "period_stock_days": 15, "closing_age_days": 19,
                    "stock_line_ids": [
                        {
                            "product_id": 801, "product_name": "Battery Module", "product_code": "BM-100",
                            "lot_id": 301, "lot_name": "LOT-001", "uom_name": "PCS",
                            "opening_quantity": 100.0, "inbound_quantity": 0.0, "outbound_quantity": 20.0,
                            "on_hand_quantity": 80.0, "reserved_quantity": 0.0, "available_quantity": 80.0,
                            "closing_location_name": "SPN/Stock/LOODS06/06", "reservation_note": "",
                        }
                    ],
                    "operation_line_ids": [
                        {
                            "direction": "outbound", "inbound_order_id": False, "inbound_order_name": "",
                            "outbound_order_id": 200, "outbound_order_name": "OUT-20260810",
                            "picking_id": 310, "picking_name": "WH/OUT/00310", "picking_state": "done",
                            "product_id": 801, "product_name": "Battery Module", "product_code": "BM-100",
                            "lot_id": 301, "lot_name": "LOT-001", "planned_quantity": 20.0,
                            "reserved_quantity": 0.0, "done_quantity": 20.0, "uom_name": "PCS",
                            "operation_datetime": "2026-08-10 14:20:00",
                            "source_location_name": "SPN/Stock/LOODS06/06", "destination_location_name": "Customers",
                        }
                    ],
                },
                {
                    "row_type": "loose", "package_id": False, "package_name": "No Pallet", "pallet_no": "",
                    "product_id": 802, "product_name": "Loose Cable", "lot_summary": "LOT-003",
                    "closing_location_name": "SPN/Stock/LOODS06/07", "lifecycle_state": "active",
                    "lifecycle_start_datetime": "2026-08-03 09:00:00", "consumed_datetime": False,
                    "inbound_order_names": "INB-20260803", "outbound_order_names": "",
                    "inbound_picking_names": "WH/IN/00121", "outbound_picking_names": "",
                    "picking_state_summary": "done: 1",
                    "opening_pallet_count": 0, "opening_product_summary": "",
                    "inbound_pallet_count": 0, "inbound_product_summary": "50 PCS",
                    "outbound_pallet_count": 0, "outbound_product_summary": "10 PCS",
                    "closing_pallet_count": 0, "closing_product_summary": "40 PCS",
                    "period_stock_days": 13, "closing_age_days": 13,
                    "stock_line_ids": [
                        {
                            "product_id": 802, "product_name": "Loose Cable", "product_code": "LC-200",
                            "lot_id": 303, "lot_name": "LOT-003", "uom_name": "PCS",
                            "opening_quantity": 0.0, "inbound_quantity": 50.0, "outbound_quantity": 10.0,
                            "on_hand_quantity": 40.0, "reserved_quantity": 0.0, "available_quantity": 40.0,
                            "closing_location_name": "SPN/Stock/LOODS06/07", "reservation_note": "",
                        }
                    ],
                    "operation_line_ids": [],
                },
            ]
            demo_summary = {
                "opening_pallet_count": 1, "inbound_pallet_count": 0,
                "outbound_pallet_count": 0, "closing_pallet_count": 1,
                "opening_product_summary": "100 PCS, 2 BOX", "inbound_product_summary": "50 PCS",
                "outbound_product_summary": "30 PCS", "closing_product_summary": "120 PCS, 2 BOX",
            }
            demo_pager = portal_pager(
                url="/my/world_depot/stock/movement_history", url_args={},
                total=2, page=page, step=20,
            )
            demo_rows_page = demo_rows[demo_pager["offset"]: demo_pager["offset"] + 20]
            demo_values = {
                "page_name": "marstek_stock_movement_history",
                "marstek_page_title": "Stock Movement History",
                "filters": filters, "summary": demo_summary,
                "rows": demo_rows_page, "pager": demo_pager, "error": "",
            }
            if "application/json" in request.httprequest.headers.get("Accept", ""):
                return request.make_json_response(demo_values)
            return request.render("marstek_stock_portal.portal_marstek_stock_history", demo_values)
        # ===== DEMO DATA END =====
        error = ""
        if not all(filters.values()):
            error = "location_id, date_from and date_to are required."
        else:
            try:
                date_from = fields.Date.to_date(filters["date_from"])
                date_to = fields.Date.to_date(filters["date_to"])
            except (TypeError, ValueError):
                error = "date_from and date_to must use YYYY-MM-DD."
            else:
                if date_from > date_to:
                    error = "date_from cannot be later than date_to."
                elif not portal_location_is_allowed(request.env, filters["location_id"]):
                    error = "location_id is not available for this portal user."
        all_rows = request.env["stock.move.line"].get_portal_stock_movement_history(filters) if not error else []
        summary = {
            "opening_pallet_count": sum(row["opening_pallet_count"] for row in all_rows),
            "inbound_pallet_count": sum(row["inbound_pallet_count"] for row in all_rows),
            "outbound_pallet_count": sum(row["outbound_pallet_count"] for row in all_rows),
            "closing_pallet_count": sum(row["closing_pallet_count"] for row in all_rows),
        }
        product_summary_map = {
            "opening_product_summary": defaultdict(float),
            "inbound_product_summary": defaultdict(float),
            "outbound_product_summary": defaultdict(float),
            "closing_product_summary": defaultdict(float),
        }
        for row in all_rows:
            for stock_line in row["stock_line_ids"]:
                product_summary_map["opening_product_summary"][stock_line["uom_name"]] += stock_line["opening_quantity"]
                product_summary_map["inbound_product_summary"][stock_line["uom_name"]] += stock_line["inbound_quantity"]
                product_summary_map["outbound_product_summary"][stock_line["uom_name"]] += stock_line["outbound_quantity"]
                product_summary_map["closing_product_summary"][stock_line["uom_name"]] += stock_line["on_hand_quantity"]
        for summary_name, summary_by_uom in product_summary_map.items():
            summary[summary_name] = ", ".join("%s %s" % ("%g" % quantity, uom_name) for uom_name, quantity in sorted(summary_by_uom.items()) if abs(quantity) > 0.000001)
        page_size = 20
        total = len(all_rows)
        pager = portal_pager(
            url="/my/world_depot/stock/movement_history",
            url_args=filters,
            total=total,
            page=page,
            step=page_size,
        )

        rows = all_rows[pager["offset"]: pager["offset"] + page_size]
        values = self.marstek_prepare_page_values("marstek_stock_movement_history", "Stock Movement History", filters)
        values.update({
            "summary": summary,
            "rows": rows,
            "pager": pager,
            "error": error,
        })
        return request.render("marstek_stock_portal.portal_marstek_stock_history", values)