# -*- coding: utf-8 -*-

from odoo import fields, http
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import ValidationError
from odoo.http import request

from ..models.utils import portal_location_is_allowed, portal_owner_partner, portal_stock_location_ids
from .portal import MarstekStockPortal


class InboundPalletSummaryPortal(MarstekStockPortal):

    @http.route("/my/world_depot/stock/inbound_pallet_summary_page", type="http", auth="user", website=True)
    def inbound_pallet_summary_page(self, **kw):
        filters = {
            "location_id": str(kw.get("location_id") or "").strip(),
            "location_name": str(kw.get("location_name") or "").strip(),
            "date_from": str(kw.get("date_from") or "").strip(),
            "date_to": str(kw.get("date_to") or "").strip(),
            "cprojectid": str(kw.get("cprojectid") or "").strip(),
        }
        values = self.marstek_prepare_page_values(
            "marstek_inbound_pallet_summary", "Inbound Pallet Summary", filters
        )
        values.update({"summary": {}, "rows": [], "pager": {}})
        return request.render("marstek_stock_portal.portal_marstek_inbound_pallet_summary_page", values)

    @http.route([
        "/my/world_depot/stock/inbound_pallet_summary",
        "/my/world_depot/stock/inbound_pallet_summary/page/<int:page>",
    ], type="http", auth="user", methods=["GET"], website=True)
    def inbound_pallet_summary_data(self, page=1, **kw):
        date_from_value = str(kw.get("date_from") or "").strip()
        date_to_value = str(kw.get("date_to") or "").strip()
        location_value = str(kw.get("location_id") or "").strip()
        cprojectid = str(kw.get("cprojectid") or "").strip()
        if not date_from_value or not date_to_value:
            return request.make_json_response({"error": "date_from and date_to are required.", "rows": []}, status=400)
        try:
            date_from = fields.Date.to_date(date_from_value)
            date_to = fields.Date.to_date(date_to_value)
        except (TypeError, ValueError):
            return request.make_json_response({"error": "date_from and date_to must use YYYY-MM-DD.", "rows": []}, status=400)
        if not date_from or not date_to or date_from > date_to:
            return request.make_json_response({"error": "date_from cannot be later than date_to.", "rows": []}, status=400)

        request_filters = {"date_from": date_from_value, "date_to": date_to_value, "location_id": location_value, "cprojectid": cprojectid}

        # ===== DEMO DATA START - 测试用，测完删除整段（含下面 if True 块） =====
        if True:
            demo_rows = [
                {
                    "first_inbound_date": "2026-06-26 09:30:00",
                    "first_inbound_datetime": "2026-06-26 07:30:00",
                    "inbound_order_id": 321,
                    "inbound_order_name": "INB-20260626-001",
                    "cproject_ids": "CP-001, CP-002",
                    "opening_pallet_count": 5,
                    "inbound_pallet_count": 2,
                    "outbound_pallet_count": 3,
                    "closing_pallet_count": 4,
                    "closing_location_summary": "SPN/Stock/LOODS13: 4",
                    "remain_period_age_days": 30,
                    "remain_total_age_days": 35,
                    "outbound_lines": [
                        {
                            "outbound_date": "2026-07-05",
                            "pallet_count": 2,
                            "stock_days": 5
                        },
                        {
                            "outbound_date": "2026-07-18",
                            "pallet_count": 1,
                            "stock_days": 18
                        }
                    ]
                },
                {
                    "first_inbound_date": "2026-06-26 09:30:00",
                    "first_inbound_datetime": "2026-06-26 08:00:00",
                    "inbound_order_id": 321,
                    "inbound_order_name": "INB-20260626-001",
                    "cproject_ids": "CP-001, CP-002",
                    "opening_pallet_count": 5,
                    "inbound_pallet_count": 3,
                    "outbound_pallet_count": 1,
                    "closing_pallet_count": 7,
                    "closing_location_summary": "SPN/Stock/LOODS06: 7",
                    "remain_period_age_days": 28,
                    "remain_total_age_days": 33,
                    "outbound_lines": [
                        {
                            "outbound_date": "2026-07-22",
                            "pallet_count": 1,
                            "stock_days": 22
                        }
                    ]
                },
                {
                    "first_inbound_date": "2026-06-26 09:30:00",
                    "first_inbound_datetime": "2026-06-26 09:30:00",
                    "inbound_order_id": 321,
                    "inbound_order_name": "INB-20260626-001",
                    "cproject_ids": "CP-001, CP-002",
                    "opening_pallet_count": 0,
                    "inbound_pallet_count": 5,
                    "outbound_pallet_count": 0,
                    "closing_pallet_count": 5,
                    "closing_location_summary": "SPN/Stock/LOODS13: 5",
                    "remain_period_age_days": 15,
                    "remain_total_age_days": 20,
                    "outbound_lines": [
                        {
                            "outbound_date": "2026-08-01",
                            "pallet_count": 3,
                            "stock_days": 10
                        },
                        {
                            "outbound_date": "2026-08-10",
                            "pallet_count": 2,
                            "stock_days": 19
                        }
                    ]
                },
                {
                    "first_inbound_date": "2026-07-01 14:00:00",
                    "first_inbound_datetime": "2026-07-01 12:00:00",
                    "inbound_order_id": 322,
                    "inbound_order_name": "INB-20260701-002",
                    "cproject_ids": "CP-003",
                    "opening_pallet_count": 0,
                    "inbound_pallet_count": 8,
                    "outbound_pallet_count": 2,
                    "closing_pallet_count": 6,
                    "closing_location_summary": "SPN/Stock/LOODS06: 4; SPN/Stock/LOODS07: 2",
                    "remain_period_age_days": 25,
                    "remain_total_age_days": 30,
                    "outbound_lines": [
                        {
                            "outbound_date": "2026-07-20",
                            "pallet_count": 2,
                            "stock_days": 20
                        }
                    ]
                },
                {
                    "first_inbound_date": "2026-07-10 08:15:00",
                    "first_inbound_datetime": "2026-07-10 06:15:00",
                    "inbound_order_id": 323,
                    "inbound_order_name": "INB-20260710-003",
                    "cproject_ids": "CP-004, CP-005, CP-006",
                    "opening_pallet_count": 0,
                    "inbound_pallet_count": 12,
                    "outbound_pallet_count": 0,
                    "closing_pallet_count": 12,
                    "closing_location_summary": "SPN/Stock/LOODS13: 12",
                    "remain_period_age_days": 20,
                    "remain_total_age_days": 20,
                    "outbound_lines": []
                },
            ]
            demo_summary = {
                "opening_pallet_count": sum(row["opening_pallet_count"] for row in demo_rows),
                "outbound_pallet_count": sum(row["outbound_pallet_count"] for row in demo_rows),
                "closing_pallet_count": sum(row["closing_pallet_count"] for row in demo_rows),
            }
            demo_pager = portal_pager(
                url="/my/world_depot/stock/inbound_pallet_summary", url_args=request_filters,
                total=len(demo_rows), page=page, step=20,
            )
            demo_rows_page = demo_rows[demo_pager["offset"]: demo_pager["offset"] + 20]
            demo_values = {
                "page_name": "marstek_inbound_pallet_summary",
                "marstek_page_title": "Inbound Pallet Summary",
                "filters": request_filters,
                "summary": demo_summary,
                "rows": demo_rows_page,
                "pager": demo_pager,
            }
            if "application/json" in request.httprequest.headers.get("Accept", ""):
                return request.make_json_response(demo_values)
            return request.render("marstek_stock_portal.portal_marstek_inbound_pallet_summary", demo_values)
        # ===== DEMO DATA END =====

        owner = portal_owner_partner(request.env)
        if not owner:
            return request.make_json_response({"error": "The portal user has no owner configured.", "rows": []}, status=403)
        filters = {"date_from": date_from, "date_to": date_to, "owner_id": owner.id, "cprojectid": cprojectid}
        if location_value == "other":
            location_model = request.env["stock.location"].sudo()
            root_location_ids = portal_stock_location_ids(request.env)
            configured_location_ids = set(location_model.search([("id", "child_of", root_location_ids)]).ids) if root_location_ids else set()
            internal_location_ids = set(location_model.search([("usage", "=", "internal")]).ids)
            filters["location_ids"] = list(internal_location_ids - configured_location_ids)
        elif location_value:
            if not portal_location_is_allowed(request.env, location_value):
                return request.make_json_response({"error": "location_id is not available for this portal user.", "rows": []}, status=400)
            filters["location_id"] = int(location_value)
        try:
            all_rows = request.env["stock.move.line"].sudo().get_inbound_pallet_summary(filters)
        except ValidationError as error:
            return request.make_json_response({"error": str(error), "rows": []}, status=400)
        pager = portal_pager(url="/my/world_depot/stock/inbound_pallet_summary", url_args=request_filters, total=len(all_rows), page=page, step=20)
        summary = {
            "opening_pallet_count": sum(row["opening_pallet_count"] for row in all_rows),
            "outbound_pallet_count": sum(row["outbound_pallet_count"] for row in all_rows),
            "closing_pallet_count": sum(row["closing_pallet_count"] for row in all_rows),
        }
        rows_page = all_rows[pager["offset"]: pager["offset"] + 20]
        # Return JSON for AJAX requests
        if "application/json" in request.httprequest.headers.get("Accept", ""):
            return request.make_json_response({
                "page_name": "marstek_inbound_pallet_summary",
                "marstek_page_title": "Inbound Pallet Summary",
                "filters": request_filters,
                "summary": summary,
                "rows": rows_page,
                "pager": pager,
            })
        # Fallback: server-side render
        values = self.marstek_prepare_page_values("marstek_inbound_pallet_summary", "Inbound Pallet Summary", request_filters)
        values.update({"summary": summary, "rows": rows_page, "pager": pager})
        return request.render("marstek_stock_portal.portal_marstek_inbound_pallet_summary", values)