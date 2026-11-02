# -*- coding: utf-8 -*-
"""Shared stock operation portal controller helpers."""
import json

from odoo import _, http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request


class StockOperationPortal(CustomerPortal):

    def _filter_values(self, kw, names):
        filters = {}
        for name in names:
            value = kw.get(name)
            if isinstance(value, str):
                value = value.strip()
            filters[name] = value or ""
        return filters

    def _prepare_page_values(self, page_name, page_title, filters=None):
        values = self._prepare_portal_layout_values()
        values.update({
            "page_name": page_name,
            "page_title": page_title,
            "filters": filters or {},
        })
        return values

    def get_request_values(self, params):
        if request.httprequest.mimetype != 'application/json':
            return params, ''
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or '{}')
        except (TypeError, ValueError):
            return {}, _('Request body must be valid JSON.')
        if not isinstance(payload, dict):
            return {}, _('Request body must be a JSON object.')
        return payload, ''

    def get_stock_operation_project_domain(self):
        user = request.env.user.sudo()
        return [('project', 'in', user.stock_operation_project_line_ids.ids)]

    @http.route(['/my/operation/products'], type='http', auth='user', website=True, methods=['GET'])
    def operation_product_search(self, **kw):
        project_id = kw.get('project_id', '')
        keyword = str(kw.get('keyword') or '').strip()
        user = request.env.user.sudo()
        project = user.stock_operation_project_line_ids.filtered(lambda item: str(item.id) == str(project_id))[:1]
        if not project or not project.category or len(keyword) < 1:
            return request.make_json_response({'products': []})
        product_domain = [('categ_id', '=', project.category.id), '|', '|', ('name', 'ilike', keyword), ('default_code', 'ilike', keyword), ('barcode', 'ilike', keyword)]
        products = request.env['product.product'].sudo().search(product_domain, order='id desc', limit=20)
        return request.make_json_response({'products': [{'id': product.id, 'default_name': product.display_name or product.name or ''} for product in products]})

    @http.route(["/my/operation"], type="http", auth="user", website=True)
    def operation_home(self, **kw):
        values = self._prepare_page_values(page_name="operation_home", page_title="Stock Operations")
        return request.render("stock_operation_portal.portal_operation_home", values)

    @http.route(["/my/operation/transfers", "/my/operation/transfers/page/<int:page>"], type="http", auth="user", website=True)
    def operation_transfers_page(self, page=1, **kw):
        filters = self._filter_values(kw, ["reference", "state", "date_from", "date_to"])
        values = self._prepare_page_values("operation_transfers", "Transfer Orders", filters)
        values["pager"] = {"total": 0, "page_count": 1}
        values["rows"] = []
        return request.render("stock_operation_portal.portal_operation_transfers", values)

    @http.route(["/my/operation/transfers/create"], type="http", auth="user", website=True, methods=["GET", "POST"])
    def operation_transfer_create(self, **kw):
        values = self._prepare_page_values("operation_transfer_create", "Create Transfer Order")
        return request.render("stock_operation_portal.portal_operation_transfer_form", values)

    @http.route(["/my/operation/transfers/<int:order_id>"], type="http", auth="user", website=True)
    def operation_transfer_detail(self, order_id, **kw):
        values = self._prepare_page_values("operation_transfer_detail", "Transfer Order Detail")
        values["order"] = None
        return request.render("stock_operation_portal.portal_operation_transfer_detail", values)
