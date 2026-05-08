# -*- coding: utf-8 -*-

from odoo import http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request
from odoo.addons.portal.controllers import portal

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
#库存总览页。
    @http.route(["/my/marstek/stock"], type="http", auth="user", website=True)
    def marstek_stock_page(self, **kw):
        filters = self.marstek_filter_values(kw, ["container_no", "bl_no", "product_code", "date_from", "date_to"])
        rows = request.env["stock.quant.package"].get_all_stock(filters)
        values = self.marstek_prepare_page_values("marstek_stock", "Stock Overview", filters)
        values.update({
            "rows": rows,
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
    @http.route(["/my/marstek/inbounds"], type="http", auth="user", website=True)
    def marstek_inbounds_page(self, **kw):
        filters = self.marstek_filter_values(kw, ["inbound_no", "bl_no", "container_no", "inbound_date_from", "inbound_date_to"])
        rows = request.env["world.depot.inbound.order"].get_inbound_list(filters)
        values = self.marstek_prepare_page_values("marstek_inbounds", "Inbound Orders", filters)
        values.update({
            "rows": rows,
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

    # @http.route(["/my/marstek/outbounds"], type="http", auth="user", website=True)
    # def marstek_outbounds_page(self, **kw):
    #     filters = self.marstek_filter_values(kw, ["outbound_no", "bl_no", "container_no", "status", "outbound_date_from", "outbound_date_to"])
    #     rows = request.env["world.depot.outbound.order"].get_outbound_list(filters)
    #     values = self.marstek_prepare_page_values("marstek_outbounds", "Outbound Orders", filters)
    #     values.update({
    #         "rows": rows,
    #     })
    #     return request.render("marstek_stock_portal.portal_marstek_outbounds", values)

class CustomerPortal(portal.CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'marstek_stock_count' in counters:
            values['marstek_stock_count'] = 1
        return values

    @http.route(['/my/marstek'], type='http', auth="user")
    def portal_marstek_home(self, **kwargs):
        values = self._prepare_portal_layout_values()
        values['page_name'] = 'marstek_home'
        return request.render("marstek_stock_portal.portal_marstek_home", values)

    @http.route(['/my/marstek/stock/overview'], type='http', auth="user")
    def portal_marstek_stock_overview(self, **kwargs):
        values = self._prepare_portal_layout_values()
        values['page_name'] = 'stock_overview'
        return request.render("marstek_stock_portal.portal_marstek_stock_overview", values)

    @http.route(['/my/marstek/container/query'], type='http', auth="user")
    def portal_marstek_container_query(self, **kwargs):
        values = self._prepare_portal_layout_values()
        values['page_name'] = 'container_query'
        values['initial_container'] = kwargs.get('container_no', '')
        return request.render("marstek_stock_portal.portal_marstek_container_query", values)

    @http.route(['/my/marstek/inbound/list'], type='http', auth="user")
    def portal_marstek_inbound_list(self, **kwargs):
        values = self._prepare_portal_layout_values()
        values['page_name'] = 'inbound_list'
        return request.render("marstek_stock_portal.portal_marstek_inbound_list", values)

    @http.route(['/my/marstek/outbound/list'], type='http', auth="user")
    def portal_marstek_outbound_list(self, **kwargs):
        values = self._prepare_portal_layout_values()
        values['page_name'] = 'outbound_list'
        return request.render("marstek_stock_portal.portal_marstek_outbound_list", values)

    @http.route(['/my/marstek/outbound/detail/<int:outbound_id>'], type='http', auth="user")
    def portal_marstek_outbound_detail(self, outbound_id=None, **kwargs):
        values = self._prepare_portal_layout_values()
        values['page_name'] = 'outbound_detail'
        values['outbound_id'] = outbound_id
        return request.render("marstek_stock_portal.portal_marstek_outbound_detail", values)

    @http.route(['/my/marstek/sn/query'], type='http', auth="user")
    def portal_marstek_sn_query(self, **kwargs):
        values = self._prepare_portal_layout_values()
        values['page_name'] = 'sn_query'
        return request.render("marstek_stock_portal.portal_marstek_sn_query", values)
