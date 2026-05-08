# -*- coding: utf-8 -*-

from odoo import http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request


class MarstekStockPortal(CustomerPortal):

    def marstek_filter_values(self, kw, names):
        filters = {}
        for name in names:
            value = kw.get(name)
            if isinstance(value, str):
                value = value.strip()
            filters[name] = value or ""
        return filters

    def marstek_prepare_page_values(self, page_name, page_title, filters=None):
        values = self._prepare_portal_layout_values()
        values.update({
            "page_name": page_name,
            "marstek_page_title": page_title,
            "filters": filters or {},
        })
        return values

    @http.route(["/my/marstek/stock"], type="http", auth="user", website=True)
    def marstek_stock_page(self, **kw):
        filters = self.marstek_filter_values(kw, ["container_no", "bl_no", "product_code", "date_from", "date_to"])
        rows = request.env["stock.quant.package"].get_all_stock(filters)
        values = self.marstek_prepare_page_values("marstek_stock", "Stock Overview", filters)
        values.update({
            "rows": rows,
        })
        return request.render("marstek_stock_portal.portal_marstek_stock", values)

    @http.route(["/my/marstek/container_stock"], type="http", auth="user", website=True)
    def marstek_container_stock_page(self, **kw):
        filters = self.marstek_filter_values(kw, ["container_no"])
        container_no = filters.get("container_no")
        stock_result = {"container_no": container_no or "", "bl_no": "", "total_quantity": 0.0, "lines": []}
        if container_no:
            stock_result = request.env["stock.quant.package"].get_stock_by_container_no(container_no)
        values = self.marstek_prepare_page_values("marstek_container_stock", "Container Stock", filters)
        values.update({
            "container_no": container_no,
            "stock_result": stock_result,
            "rows": stock_result.get("lines", []),
        })
        return request.render("marstek_stock_portal.portal_marstek_container_stock", values)

    @http.route(["/my/marstek/inbounds"], type="http", auth="user", website=True)
    def marstek_inbounds_page(self, **kw):
        filters = self.marstek_filter_values(kw, ["inbound_no", "bl_no", "container_no", "inbound_date_from", "inbound_date_to"])
        rows = request.env["world.depot.inbound.order"].get_inbound_list(filters)
        values = self.marstek_prepare_page_values("marstek_inbounds", "Inbound Orders", filters)
        values.update({
            "rows": rows,
        })
        return request.render("marstek_stock_portal.portal_marstek_inbounds", values)

    @http.route(["/my/marstek/inbounds/<int:inbound_id>"], type="http", auth="user", website=True)
    def marstek_inbound_detail_page(self, inbound_id, **kw):
        inbound_env = request.env["world.depot.inbound.order"]

        order = inbound_env.get_inbound_order(inbound_id)
        if not order:
            return request.redirect("/my/marstek/inbounds")

        detail_rows = inbound_env.get_inbound_detail(inbound_id)
        attachment_rows = inbound_env.get_inbound_attachments(inbound_id)

        values = self.marstek_prepare_page_values("marstek_inbound_detail", "Inbound Detail")
        values.update({
            "order": order,
            "detail_rows": detail_rows,
            "attachment_rows": attachment_rows,
        })
        return request.render("marstek_stock_portal.portal_marstek_inbound_detail", values)

    # @http.route(["/my/marstek/outbounds"], type="http", auth="user", website=True)
    # def marstek_outbounds_page(self, **kw):
    #     filters = self.marstek_filter_values(kw, ["outbound_no", "bl_no", "container_no", "status", "outbound_date_from", "outbound_date_to"])
    #     rows = request.env["world.depot.outbound.order"].get_outbound_list(filters)
    #     values = self.marstek_prepare_page_values("marstek_outbounds", "Outbound Orders", filters)
    #     values.update({
    #         "rows": rows,
    #     })
    #     return request.render("marstek_stock_portal.portal_marstek_outbounds", values)
