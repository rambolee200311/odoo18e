# -*- coding: utf-8 -*-

from odoo import http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request
from odoo.addons.portal.controllers import portal
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
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

    #Marstek库存模块主菜单页(点击卡片后进入的菜单页面)

    @http.route(["/my/marstek"], type="http", auth="user", website=True)
    def manstek_home(self, **kw):
        values = self.marstek_prepare_page_values(
            page_name="marstek_home",
            page_title="Manstek Stock"
        )
        return request.render("marstek_stock_portal.portal_marstek_home", values)

#库存总览页。
    @http.route(["/my/marstek/stock", "/my/marstek/stock/page/<int:page>"], type="http", auth="user", website=True)
    def marstek_stock_page(self, page=1, **kw):
        filters = self.marstek_filter_values(kw, ["container_no", "bl_no", "product_code", "date_from", "date_to", "view_mode"])
        page_size = 20
        all_rows = request.env["stock.quant.package"].get_all_stock(filters)
        total = len(all_rows)
        pager = portal_pager(
            url="/my/marstek/stock",
            url_args=filters,
            total=total,
            page=page,
            step=page_size,
        )
        pager["total"] = total


        rows = all_rows[pager["offset"]: pager["offset"] + page_size]
        values = self.marstek_prepare_page_values("marstek_stock", "Stock Overview", filters)
        values.update({
            "rows": rows,
            "pager": pager,
        })
        return request.render("marstek_stock_portal.portal_marstek_stock", values)

   # 按柜号查询库存页。
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

    #入库查询页。
    @http.route(["/my/marstek/inbounds","/my/marstek/inbounds/page/<int:page>"], type="http", auth="user", website=True)
    def marstek_inbounds_page(self,page=1, **kw):
        filters = self.marstek_filter_values(kw, ["inbound_no", "bl_no","reference", "container_no", "inbound_date_from", "inbound_date_to","portal_inbound_status", "view_mode"])
        page_size = 20
        all_rows = request.env["world.depot.inbound.order"].get_inbound_list(filters)
        total = len(all_rows)
        pager = portal_pager(
            url="/my/marstek/inbounds",
            url_args=filters,
            total=total,
            page=page,
            step=page_size,
        )
        pager["total"] = total
        rows =all_rows[pager["offset"]: pager["offset"] + page_size]

        values = self.marstek_prepare_page_values("marstek_inbounds", "Inbound Orders", filters)
        values.update({
            "rows": rows,
            "pager": pager,
        })
        return request.render("marstek_stock_portal.portal_marstek_inbounds", values)


#获取指定入库单下的托盘明细数据和获取指定入库单的可下载附件列表
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


#出库查询页
    @http.route(["/my/marstek/outbounds","/my/marstek/outbounds/page/<int:page>"], type="http", auth="user", website=True)
    def marstek_outbounds_page(self, page=1, **kw):
        filters = self.marstek_filter_values(kw,
                                             ["outbound_no", "bl_no", "container_no", "portal_outbound_status", "outbound_date_from",
                                              "outbound_date_to", "view_mode"])
        page_size = 20
        all_rows = request.env["world.depot.outbound.order"].get_outbound_list(filters)
        total = len(all_rows)
        pager = portal_pager(
            url="/my/marstek/outbounds",
            url_args=filters,
            total=total,
            page=page,
            step=page_size,
        )
        pager["total"] = total
        rows = all_rows[pager["offset"]: pager["offset"] + page_size]

        values = self.marstek_prepare_page_values("marstek_outbounds", "Outbound Orders", filters)
        values.update({
            "rows": rows,
            "pager": pager,
        })
        return request.render("marstek_stock_portal.portal_marstek_outbounds", values)

    #获取指定出库单下的托盘明细数据
    @http.route(["/my/marstek/outbounds/<int:outbound_id>", "/my/marstek/outbounds/<int:outbound_id>/page/<int:page>"], type="http", auth="user", website=True)
    def marstek_outbound_detail_page(self, outbound_id, page=1, **kw):
        filters = self.marstek_filter_values(kw, ["view_mode"])
        outbound_env = request.env["world.depot.outbound.order"]
        order = outbound_env.get_outbound_order(outbound_id)
        if not order:
            return request.redirect("/my/marstek/outbounds")

        page_size = 10
        all_detail_rows = outbound_env.get_outbound_detail(outbound_id)
        total = len(all_detail_rows)
        pager = portal_pager(
            url=f"/my/marstek/outbounds/{outbound_id}",
            url_args=filters,
            total=total,
            page=page,
            step=page_size,
        )
        pager["total"] = total
        detail_rows = all_detail_rows[pager["offset"]: pager["offset"] + page_size]
        attachment_rows = outbound_env.get_outbound_attachments(outbound_id)

        values = self.marstek_prepare_page_values("marstek_outbound_detail", "Outbound Detail",filters)
        values.update({
            "order": order,
            "detail_rows": detail_rows,
            "attachment_rows": attachment_rows,
            "detail_pager": pager,
        })
        return request.render("marstek_stock_portal.portal_marstek_outbound_detail", values)

    @http.route(["/my/marstek/sn_query"], type="http", auth="user", website=True)
    def marstek_sn_query_page(self, **kw):
        filters = self.marstek_filter_values(kw, ["sn_code", "view_mode"])
        sn_code = filters.get("sn_code")
        sn_result = {"status": "", "data": {}}

        if sn_code:
            sn_result = request.env["world.depot.outbound.order.sn.detail"].search_sn(sn_code)

        values = self.marstek_prepare_page_values("marstek_sn_query", "SN Query", filters)
        values.update({
            "sn_code": sn_code,
            "sn_result": sn_result,
        })
        return request.render("marstek_stock_portal.portal_marstek_sn_query", values)


