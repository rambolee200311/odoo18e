# -*- coding: utf-8 -*-
"""
Stock Operation Portal Controllers
"""
from odoo import http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request
from odoo.addons.portal.controllers import portal
from odoo.addons.portal.controllers.portal import pager as portal_pager


class StockOperationPortal(CustomerPortal):
    """Stock Operation Portal - Handles Inbound, Outbound and Transfer orders"""

    # ============================================================
    # 工具方法
    # ============================================================

    def _filter_values(self, kw, names):
        """解析过滤参数"""
        filters = {}
        for name in names:
            value = kw.get(name)
            if isinstance(value, str):
                value = value.strip()
            filters[name] = value or ""
        return filters

    def _prepare_page_values(self, page_name, page_title, filters=None):
        """准备页面基础数据"""
        values = self._prepare_portal_layout_values()
        values.update({
            "page_name": page_name,
            "page_title": page_title,
            "filters": filters or {},
        })
        return values

    # ============================================================
    # 主页
    # ============================================================

    @http.route(["/my/operation"], type="http", auth="user", website=True)
    def operation_home(self, **kw):
        """操作门户主页"""
        values = self._prepare_page_values(
            page_name="operation_home",
            page_title="Stock Operations"
        )
        return request.render("stock_operation_portal.portal_operation_home", values)

    # ============================================================
    # 入库订单
    # ============================================================

    @http.route(["/my/operation/inbounds", "/my/operation/inbounds/page/<int:page>"],
                type="http", auth="user", website=True)
    def operation_inbounds_page(self, page=1, **kw):
        """入库订单列表页"""
        filters = self._filter_values(kw, ["reference", "bl_no", "container_no",
                                           "state", "date_from", "date_to"])
        values = self._prepare_page_values("operation_inbounds", "Inbound Orders", filters)
        values["pager"] = {"total": 0, "page_count": 1}
        values["rows"] = []
        return request.render("stock_operation_portal.portal_operation_inbounds", values)

    @http.route(["/my/operation/inbounds/create"], type="http", auth="user", website=True,
                methods=["GET", "POST"])
    def operation_inbound_create(self, **kw):
        """创建入库订单"""
        values = self._prepare_page_values("operation_inbound_create", "Create Inbound Order")
        return request.render("stock_operation_portal.portal_operation_inbound_form", values)

    @http.route(["/my/operation/inbounds/<int:order_id>"], type="http", auth="user", website=True)
    def operation_inbound_detail(self, order_id, **kw):
        """入库订单详情页"""
        values = self._prepare_page_values("operation_inbound_detail", "Inbound Order Detail")
        values["order"] = None
        values["detail_rows"] = []
        values["attachment_rows"] = []
        return request.render("stock_operation_portal.portal_operation_inbound_detail", values)

    # ============================================================
    # 出库订单
    # ============================================================

    @http.route(["/my/operation/outbounds", "/my/operation/outbounds/page/<int:page>"],
                type="http", auth="user", website=True)
    def operation_outbounds_page(self, page=1, **kw):
        """出库订单列表页"""
        filters = self._filter_values(kw, ["reference", "bl_no", "container_no",
                                           "state", "date_from", "date_to"])
        values = self._prepare_page_values("operation_outbounds", "Outbound Orders", filters)
        values["pager"] = {"total": 0, "page_count": 1}
        values["rows"] = []
        return request.render("stock_operation_portal.portal_operation_outbounds", values)

    @http.route(["/my/operation/outbounds/create"], type="http", auth="user", website=True,
                methods=["GET", "POST"])
    def operation_outbound_create(self, **kw):
        """创建出库订单"""
        values = self._prepare_page_values("operation_outbound_create", "Create Outbound Order")
        return request.render("stock_operation_portal.portal_operation_outbound_form", values)

    @http.route(["/my/operation/outbounds/<int:order_id>"], type="http", auth="user", website=True)
    def operation_outbound_detail(self, order_id, **kw):
        """出库订单详情页"""
        values = self._prepare_page_values("operation_outbound_detail", "Outbound Order Detail")
        values["order"] = None
        values["detail_rows"] = []
        return request.render("stock_operation_portal.portal_operation_outbound_detail", values)

    # ============================================================
    # 仓内操作/调拨订单
    # ============================================================

    @http.route(["/my/operation/transfers", "/my/operation/transfers/page/<int:page>"],
                type="http", auth="user", website=True)
    def operation_transfers_page(self, page=1, **kw):
        """调拨订单列表页"""
        filters = self._filter_values(kw, ["reference", "state", "date_from", "date_to"])
        values = self._prepare_page_values("operation_transfers", "Transfer Orders", filters)
        values["pager"] = {"total": 0, "page_count": 1}
        values["rows"] = []
        return request.render("stock_operation_portal.portal_operation_transfers", values)

    @http.route(["/my/operation/transfers/create"], type="http", auth="user", website=True,
                methods=["GET", "POST"])
    def operation_transfer_create(self, **kw):
        """创建调拨订单"""
        values = self._prepare_page_values("operation_transfer_create", "Create Transfer Order")
        return request.render("stock_operation_portal.portal_operation_transfer_form", values)

    @http.route(["/my/operation/transfers/<int:order_id>"], type="http", auth="user", website=True)
    def operation_transfer_detail(self, order_id, **kw):
        """调拨订单详情页"""
        values = self._prepare_page_values("operation_transfer_detail", "Transfer Order Detail")
        values["order"] = None
        return request.render("stock_operation_portal.portal_operation_transfer_detail", values)
