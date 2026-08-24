# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import fields, http
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.http import request

from ..models.utils import portal_location_is_allowed
from .portal import MarstekStockPortal



class StockMovementHistoryPortal(MarstekStockPortal):

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
    ], type="http", auth="user", methods=["GET"], website=False)
    def stock_movement_history_portal(self, page=1, **kw):
        filters = {
            "location_id": str(kw.get("location_id") or "").strip(),
            "date_from": str(kw.get("date_from") or "").strip(),
            "date_to": str(kw.get("date_to") or "").strip(),
        }
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
        pager["total"] = total
        rows = all_rows[pager["offset"]: pager["offset"] + page_size]
        values = {
            "page_name": "marstek_stock_movement_history",
            "marstek_page_title": "Stock Movement History",
            "filters": filters,
            "summary": summary,
            "rows": rows,
            "pager": pager,
            "error": error,
        }
        return request.make_json_response(values, status=400 if error else 200)
