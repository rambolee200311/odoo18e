# -*- coding: utf-8 -*-

from odoo import fields, http
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import ValidationError
from odoo.http import request

from ..models.utils import portal_location_is_allowed, portal_owner_partner, portal_stock_location_ids
from .portal import MarstekStockPortal


class InboundPalletSummaryPortal(MarstekStockPortal):

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
        request_filters = {"date_from": fields.Date.to_string(date_from), "date_to": fields.Date.to_string(date_to), "location_id": location_value, "cprojectid": cprojectid}
        pager = portal_pager(url="/my/world_depot/stock/inbound_pallet_summary", url_args=request_filters, total=len(all_rows), page=page, step=20)
        summary = {
            "opening_pallet_count": sum(row["opening_pallet_count"] for row in all_rows),
            #"inbound_pallet_count": sum(row["inbound_pallet_count"] for row in all_rows),
            "outbound_pallet_count": sum(row["outbound_pallet_count"] for row in all_rows),
            "closing_pallet_count": sum(row["closing_pallet_count"] for row in all_rows),
        }
        values = self.marstek_prepare_page_values("marstek_inbound_pallet_summary", "Inbound Pallet Summary", request_filters)
        values.update({"summary": summary, "rows": all_rows[pager["offset"]: pager["offset"] + 20], "pager": pager})
        return request.render("marstek_stock_portal.portal_marstek_inbound_pallet_summary", values)
