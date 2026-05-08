# -*- coding: utf-8 -*-
"""
Marstek Stock Portal Controller
"""

from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers import portal


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
