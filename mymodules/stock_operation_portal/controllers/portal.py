# -*- coding: utf-8 -*-
"""
Stock Operation Portal Controllers
"""
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

    def get_inbound_line_values(self, form, project):
        product_ids = form.getlist('product_id')
        pallet_values = form.getlist('pallets')
        quantity_values = form.getlist('quantity')
        weight_values = form.getlist('weight')
        pallet_no_values = form.getlist('pallet_no')
        remark_values = form.getlist('line_remark')
        lines = []
        for index, product_id in enumerate(product_ids):
            if not product_id:
                continue
            product = request.env['product.product'].sudo().search([('id', '=', product_id), ('categ_id', '=', project.category.id)], limit=1)
            try:
                pallets = float(pallet_values[index] or 0)
                quantity = float(quantity_values[index] or 0)
                weight = float(weight_values[index] or 0)
            except (IndexError, ValueError):
                return [], _('Pallets, quantity, and weight must be valid numbers.')
            if not product or pallets <= 0 or quantity <= 0 or weight < 0:
                return [], _('Every product line must use an allowed product, positive pallets and quantity, and a non-negative weight.')
            lines.append((0, 0, {
                'pallets': pallets,
                'pallet_no': pallet_no_values[index] if index < len(pallet_no_values) else '',
                'remark': remark_values[index] if index < len(remark_values) else '',
                'inbound_order_product_pallet_ids': [(0, 0, {'product_id': product.id, 'quantity': quantity, 'weight': weight})],
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
        projects = user.stock_operation_project_line_ids
        project_id = kw.get('project_id', '')
        active_project = projects.filtered(lambda project: str(project.id) == str(project_id))
        values = self._prepare_page_values("operation_inbound_create", "Create Inbound Order")
        values.update({
            'projects': projects,
            'active_project': active_project,
            'products': request.env['product.product'].sudo().search([('categ_id', '=', active_project.category.id)]) if active_project and active_project.category else request.env['product.product'].sudo(),
            'form_values': kw,
        })
        if not projects:
            values['error'] = _('Your portal user is not assigned Stock Operation projects. Please contact an administrator.')
            return request.render("stock_operation_portal.portal_operation_inbound_form", values)
        if request.httprequest.method == 'POST':
            if not active_project:
                values['error'] = _('Please select an available project.')
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            if not active_project.category:
                values['error'] = _('The selected project has no product category.')
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            if not kw.get('reference', '').strip() or not kw.get('a_date'):
                values['error'] = _('Reference and arrival date are required.')
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            lines, error = self.get_inbound_line_values(request.httprequest.form, active_project)
            if error:
                values['error'] = error
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            try:
                order = request.env['world.depot.inbound.order'].create({
                    'type': 'inbound', 'date': fields.Date.today(), 'a_date': kw['a_date'], 'project': active_project.id,
                    'reference': kw['reference'].strip(), 'bl_no': kw.get('bl_no', '').strip(), 'cntr_no': kw.get('cntr_no', '').strip(),
                    'remark': kw.get('remark', '').strip(), 'is_scan_sn': kw.get('is_scan_sn') == 'on', 'inbound_order_product_ids': lines,
                })
            except ValidationError as error:
                values['error'] = error.args[0]
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            return request.redirect('/my/operation/inbounds/%s' % order.id)
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
