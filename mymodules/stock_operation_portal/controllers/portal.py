# -*- coding: utf-8 -*-
"""
Stock Operation Portal Controllers
"""
import json

from odoo import _, fields, http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
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

    def get_inbound_request_values(self, params):
        if request.httprequest.mimetype != 'application/json':
            return params, ''
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or '{}')
        except (TypeError, ValueError):
            return {}, _('Request body must be valid JSON.')
        if not isinstance(payload, dict):
            return {}, _('Request body must be a JSON object.')
        return payload, ''

    def get_inbound_line_values(self, line_values, project):
        if not isinstance(line_values, list):
            return [], _('The lines field must be a list.')
        lines = []
        for line_value in line_values:
            if not isinstance(line_value, dict):
                return [], _('Every inbound line must be a JSON object.')
            try:
                pallets = float(line_value.get('pallets') or 0)
            except (TypeError, ValueError):
                return [], _('Pallets must be a valid number.')
            if pallets <= 0:
                return [], _('Every pallet line must have positive pallets.')
            products = line_value.get('products')
            if not isinstance(products, list) or not products:
                return [], _('Every pallet line must contain at least one product.')
            product_lines = []
            for product_value in products:
                if not isinstance(product_value, dict):
                    return [], _('Every product line must be a JSON object.')
                product_id = product_value.get('product_id')
                product = request.env['product.product'].sudo().search([('id', '=', product_id), ('categ_id', '=', project.category.id)], limit=1)
                try:
                    quantity = float(product_value.get('quantity') or 0)
                    product_template = product.product_tmpl_id
                    default_gross_weight = getattr(product_template, 'gross_weight', 0.0) or product.weight or 0.0
                    default_net_weight = getattr(product_template, 'net_weight', 0.0) or 0.0
                    gross_weight = float(product_value.get('gross_weight') if product_value.get('gross_weight') not in (None, '') else default_gross_weight)
                    net_weight = float(product_value.get('net_weight') if product_value.get('net_weight') not in (None, '') else default_net_weight)
                except (TypeError, ValueError):
                    return [], _('Quantity, gross weight, and net weight must be valid numbers.')
                if not product or quantity <= 0 or gross_weight < 0 or net_weight < 0:
                    return [], _('Every product line must use an allowed product, positive quantity, and non-negative gross and net weight.')
                product_lines.append((0, 0, {
                    'product_id': product.id,
                    'quantity': quantity,
                    'stock_operation_gross_weight': gross_weight,
                    'stock_operation_net_weight': net_weight,
                    'remark': str(product_value.get('remark') or '').strip(),
                }))
            lines.append((0, 0, {
                'pallets': pallets,
                'pallet_no': str(line_value.get('pallet_no') or '').strip(),
                'pallet_type': str(line_value.get('pallet_type') or '').strip(),
                'remark': str(line_value.get('remark') or '').strip(),
                'inbound_order_product_pallet_ids': product_lines,
            }))
        return lines, _('Add at least one product line.') if not lines else ''

    def get_inbound_picking(self, order_id):
        return request.env['stock.picking'].sudo().search([('inbound_order_id', '=', order_id)], limit=1)

    def get_stock_operation_project_domain(self):
        user = request.env.user.sudo()
        return [('project', 'in', user.stock_operation_project_line_ids.ids)]

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
        domain = self.get_stock_operation_project_domain()
        if filters['reference']:
            domain.append(('reference', 'ilike', filters['reference']))
        if filters['bl_no']:
            domain.append(('bl_no', 'ilike', filters['bl_no']))
        if filters['container_no']:
            domain.append(('cntr_no', 'ilike', filters['container_no']))
        if filters['state'] == 'new':
            domain.extend([('state', '=', 'new'), ('stock_operation_portal_confirmed', '=', False)])
        elif filters['state'] == 'portal_confirmed':
            domain.extend([('state', '=', 'new'), ('stock_operation_portal_confirmed', '=', True)])
        elif filters['state']:
            domain.append(('state', '=', filters['state']))
        if filters['date_from']:
            domain.append(('a_date', '>=', filters['date_from']))
        if filters['date_to']:
            domain.append(('a_date', '<=', filters['date_to']))
        inbound_model = request.env['world.depot.inbound.order'].sudo()
        total = inbound_model.search_count(domain)
        pager = portal_pager(url='/my/operation/inbounds', url_args=filters, total=total, page=page, step=20)
        orders = inbound_model.search(domain, order='id desc', offset=pager['offset'], limit=20)
        values.update({
            'pager': pager,
            'rows': [{'id': order.id, 'reference': order.reference, 'bl_no': order.bl_no, 'container_no': order.cntr_no,
                      'expected_date': fields.Date.to_string(order.a_date) if order.a_date else '',
                      'state': 'portal_confirmed' if order.state == 'new' and order.stock_operation_portal_confirmed else order.state,
                      'portal_confirmed': order.stock_operation_portal_confirmed} for order in orders],
        })
        return request.render("stock_operation_portal.portal_operation_inbounds", values)

    @http.route(["/my/operation/inbounds/create"], type="http", auth="user", website=True,
                methods=["GET", "POST"])
    def operation_inbound_create(self, **kw):
        user = request.env.user.sudo()
        project_records = user.stock_operation_project_line_ids
        payload, payload_error = self.get_inbound_request_values(kw) if request.httprequest.method == 'POST' else (kw, '')
        project_id = payload.get('project_id', '')
        active_project_record = project_records.filtered(lambda project: str(project.id) == str(project_id))[:1]
        product_records = request.env['product.product'].sudo().search([('categ_id', '=', active_project_record.category.id)]) if active_project_record and active_project_record.category else request.env['product.product'].sudo()
        form_values = {'reference': '', 'date': '', 'a_date': '', 'project_id': project_id or None, 'bl_no': '', 'cntr_no': '', 'is_adr': True, 'remark': '', 'lines': []}
        form_values.update(payload)
        values = self._prepare_page_values("operation_inbound_create", "Create Inbound Order")
        values.update({
            'projects': [{'id': project.id, 'name': project.name or ''} for project in project_records],
            'active_project': {'id': active_project_record.id, 'name': active_project_record.name or ''} if active_project_record else None,
            'products': [{'id': product.id, 'default_name': product.display_name or product.name or ''} for product in product_records],
            'form_values': form_values,
            'attachment_rows': [],
        })
        if not project_records:
            values['error'] = _('Your portal user is not assigned Stock Operation projects. Please contact an administrator.')
            return request.render("stock_operation_portal.portal_operation_inbound_form", values)
        if request.httprequest.method == 'POST':
            if payload_error:
                values['error'] = payload_error
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            if not active_project_record:
                values['error'] = _('Please select an available project.')
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            if not active_project_record.category:
                values['error'] = _('The selected project has no product category.')
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            if not str(payload.get('reference') or '').strip() or not payload.get('date') or not payload.get('a_date'):
                values['error'] = _('Reference, order date, and arrival date are required.')
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            if 'is_adr' in payload and not isinstance(payload['is_adr'], bool):
                values['error'] = _('is_adr must be a boolean.')
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            lines, error = self.get_inbound_line_values(payload.get('lines'), active_project_record)
            if error:
                values['error'] = error
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            try:
                order = request.env['world.depot.inbound.order'].create({
                    'type': 'inbound', 'date': payload['date'], 'a_date': payload['a_date'], 'project': active_project_record.id,
                    'reference': str(payload['reference']).strip(), 'bl_no': str(payload.get('bl_no') or '').strip(), 'cntr_no': str(payload.get('cntr_no') or '').strip(),
                    'is_adr': payload.get('is_adr', True), 'remark': str(payload.get('remark') or '').strip(), 'inbound_order_product_ids': lines,
                })
            except ValidationError as error:
                values['error'] = error.args[0]
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            return request.redirect('/my/operation/inbounds/%s' % order.id)
        return request.render("stock_operation_portal.portal_operation_inbound_form", values)

    @http.route(["/my/operation/inbounds/<int:order_id>/edit"], type="http", auth="user", website=True,
                methods=["GET", "POST"])
    def operation_inbound_edit(self, order_id, **kw):
        inbound_model = request.env['world.depot.inbound.order']
        order_sudo = inbound_model.sudo().search([('id', '=', order_id), ('state', '=', 'new'), (
        'stock_operation_portal_confirmed', '=', False)] + self.get_stock_operation_project_domain(), limit=1)
        if not order_sudo:
            return request.not_found()
        payload, payload_error = self.get_inbound_request_values(kw) if request.httprequest.method == 'POST' else (kw, '')
        values = self._prepare_page_values("operation_inbound_edit", "Edit Inbound Order")
        values.update({'order': order_sudo, 'detail_rows': inbound_model.get_inbound_detail_grouped(order_id),
                       'attachment_rows': inbound_model.get_inbound_attachments(order_id)})
        if request.httprequest.method == 'POST':
            if payload_error:
                values['error'] = payload_error
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            reference = str(payload.get('reference') or order_sudo.reference or '').strip()
            arrival_date = payload.get('a_date', fields.Date.to_string(order_sudo.a_date) if order_sudo.a_date else '')
            if not reference or not arrival_date:
                values['error'] = _('Reference and arrival date are required.')
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            write_values = {
                'reference': reference, 'a_date': arrival_date, 'bl_no': str(payload.get('bl_no') or '').strip(),
                'cntr_no': str(payload.get('cntr_no') or '').strip(), 'remark': str(payload.get('remark') or '').strip(),
                'is_scan_sn': payload.get('is_scan_sn') is True,
            }
            if 'lines' in payload:
                lines, error = self.get_inbound_line_values(payload.get('lines'), order_sudo.project)
                if error:
                    values['error'] = error
                    return request.render("stock_operation_portal.portal_operation_inbound_form", values)
                write_values['inbound_order_product_ids'] = [(5, 0, 0)] + lines
            try:
                inbound_model.browse(order_sudo.id).write(write_values)
            except ValidationError as error:
                values['error'] = error.args[0]
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            return request.redirect('/my/operation/inbounds/%s' % order_sudo.id)
        return request.render("stock_operation_portal.portal_operation_inbound_form", values)

    @http.route(["/my/operation/inbounds/<int:order_id>"], type="http", auth="user", website=True)
    def operation_inbound_detail(self, order_id, **kw):
        """入库订单详情页"""
        inbound_env = request.env["world.depot.inbound.order"]
        order = inbound_env.get_inbound_order(order_id)
        if not order:
            return request.not_found()
        values = self._prepare_page_values("operation_inbound_detail", "Inbound Order Detail")
        values.update({'order': order, 'detail_rows': inbound_env.get_inbound_detail_grouped(order_id), 'attachment_rows': inbound_env.get_inbound_attachments(order_id)})
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
