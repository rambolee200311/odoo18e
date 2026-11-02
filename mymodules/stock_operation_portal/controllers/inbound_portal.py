# -*- coding: utf-8 -*-

from odoo import _, fields, http
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from ..models.utils import portal_product_name
from .portal import StockOperationPortal


class StockOperationInboundPortal(StockOperationPortal):

    def get_inbound_line_values(self, line_values, project, order=None, deleted_line_ids=None):
        if not isinstance(line_values, list):
            return [], _('The lines field must be a list.')
        lines = []
        pallet_no_keys = set()
        deleted_line_ids = deleted_line_ids or set()
        for line_value in line_values:
            if not isinstance(line_value, dict):
                return [], _('Every inbound line must be a JSON object.')
            line_id = line_value.get('id')
            existing_line = order.inbound_order_product_ids.filtered(lambda line: line.id == int(line_id))[:1] if order and line_id not in (None, '') and str(line_id).isdigit() else order.inbound_order_product_ids[:0] if order else None
            if line_id not in (None, '') and not existing_line:
                return [], _('Every pallet line id must belong to the current inbound order.')
            if existing_line and existing_line.id in deleted_line_ids:
                return [], _('A pallet line cannot be updated and deleted in the same request.')
            try:
                pallets = float(line_value.get('pallets') if 'pallets' in line_value else (existing_line.pallets if existing_line else 0))
            except (TypeError, ValueError):
                return [], _('Pallets must be a valid number.')
            if pallets <= 0:
                return [], _('Every pallet line must have positive pallets.')
            pallet_no = str((line_value.get('pallet_no') or '') if 'pallet_no' in line_value else (existing_line.pallet_no if existing_line else '') or '').strip()
            if order is None:
                if not pallet_no:
                    return [], _('Every pallet line must have a pallet number.')
                pallet_no_key = pallet_no.casefold()
                if pallet_no_key in pallet_no_keys:
                    return [], _('Pallet numbers cannot be duplicated.')
                pallet_no_keys.add(pallet_no_key)
            products = line_value.get('products') if 'products' in line_value else None
            if products is None and not existing_line:
                return [], _('Every new pallet line must contain products.')
            if products is not None and (not isinstance(products, list) or not products):
                return [], _('Every pallet line must contain at least one product.')
            product_lines = []
            submitted_product_line_ids = set()
            deleted_product_ids = line_value.get('deleted_product_ids', [])
            if not isinstance(deleted_product_ids, list):
                return [], _('deleted_product_ids must be a list.')
            if deleted_product_ids and not existing_line:
                return [], _('Only existing product lines can be deleted.')
            deleted_product_line_ids = set()
            for product_line_id in deleted_product_ids:
                if not str(product_line_id).isdigit() or int(product_line_id) in deleted_product_line_ids:
                    return [], _('deleted_product_ids must contain unique product line ids.')
                deleted_product_line = existing_line.inbound_order_product_pallet_ids.filtered(lambda product_line: product_line.id == int(product_line_id))[:1]
                if not deleted_product_line:
                    return [], _('Every deleted product line id must belong to its pallet line.')
                deleted_product_line_ids.add(deleted_product_line.id)
            if products is not None:
                for product_value in products:
                    if not isinstance(product_value, dict):
                        return [], _('Every product line must be a JSON object.')
                    product_line_id = product_value.get('id')
                    existing_product_line = existing_line.inbound_order_product_pallet_ids.filtered(lambda product_line: product_line.id == int(product_line_id))[:1] if existing_line and product_line_id not in (None, '') and str(product_line_id).isdigit() else existing_line.inbound_order_product_pallet_ids[:0] if existing_line else None
                    if product_line_id not in (None, '') and not existing_product_line:
                        return [], _('Every product line id must belong to its pallet line.')
                    if existing_product_line and existing_product_line.id in submitted_product_line_ids:
                        return [], _('Every product line id can only be submitted once.')
                    if existing_product_line:
                        submitted_product_line_ids.add(existing_product_line.id)
                    if existing_product_line and existing_product_line.id in deleted_product_line_ids:
                        return [], _('A product line cannot be updated and deleted in the same request.')
                    product_id = product_value.get('product_id') if 'product_id' in product_value else existing_product_line.product_id.id if existing_product_line else False
                    product = request.env['product.product'].sudo().search([('id', '=', product_id), ('categ_id', '=', project.category.id)], limit=1)
                    try:
                        quantity = float(product_value.get('quantity') if 'quantity' in product_value else (existing_product_line.quantity if existing_product_line else 0))
                        product_template = product.product_tmpl_id
                        default_gross_weight = getattr(product_template, 'gross_weight', 0.0) or product.weight or 0.0
                        default_net_weight = getattr(product_template, 'net_weight', 0.0) or 0.0
                        gross_weight = float(product_value.get('gross_weight') if product_value.get('gross_weight') not in (None, '') else (existing_product_line.stock_operation_gross_weight if existing_product_line else default_gross_weight))
                        net_weight = float(product_value.get('net_weight') if product_value.get('net_weight') not in (None, '') else (existing_product_line.stock_operation_net_weight if existing_product_line else default_net_weight))
                    except (TypeError, ValueError):
                        return [], _('Quantity, gross weight, and net weight must be valid numbers.')
                    if not product or quantity <= 0 or gross_weight < 0 or net_weight < 0:
                        return [], _('Every product line must use an allowed product, positive quantity, and non-negative gross and net weight.')
                    product_values = {
                        'product_id': product.id,
                        'quantity': quantity,
                        'stock_operation_gross_weight': gross_weight,
                        'stock_operation_net_weight': net_weight,
                        'remark': str((product_value.get('remark') or '') if 'remark' in product_value else (existing_product_line.remark if existing_product_line else '') or '').strip(),
                    }
                    if not existing_product_line:
                        product_values['creation_source'] = 'portal'
                    product_lines.append((1, existing_product_line.id, product_values) if existing_product_line else (0, 0, product_values))
            if existing_line and deleted_product_line_ids:
                remaining_product_lines = existing_line.inbound_order_product_pallet_ids.filtered(lambda product_line: product_line.id not in deleted_product_line_ids)
                if not remaining_product_lines and not any(product_line[0] == 0 for product_line in product_lines):
                    return [], _('Every pallet line must contain at least one product.')
                product_lines.extend((2, product_line_id, 0) for product_line_id in sorted(deleted_product_line_ids))
            line_data = {
                'pallets': pallets,
                'pallet_no': pallet_no,
                'pallet_type': str((line_value.get('pallet_type') or '') if 'pallet_type' in line_value else (existing_line.pallet_type if existing_line else '') or '').strip(),
                'remark': str((line_value.get('remark') or '') if 'remark' in line_value else (existing_line.remark if existing_line else '') or '').strip(),
            }
            if products is not None or deleted_product_line_ids:
                line_data['inbound_order_product_pallet_ids'] = product_lines
            if not existing_line:
                line_data['creation_source'] = 'portal'
            lines.append((1, existing_line.id, line_data) if existing_line else (0, 0, line_data))
        return lines, _('Add at least one product line.') if not lines else ''

    def get_inbound_picking(self, order_id):
        return request.env['stock.picking'].sudo().search([('inbound_order_id', '=', order_id)], limit=1)

    @http.route(["/my/operation/inbounds", "/my/operation/inbounds/page/<int:page>"], type="http", auth="user", website=True)
    def operation_inbounds_page(self, page=1, **kw):
        filters = self._filter_values(kw, ["reference", "bl_no", "container_no", "state", "date_from", "date_to"])
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

    @http.route(["/my/operation/inbounds/create"], type="http", auth="user", website=True, methods=["GET", "POST"], csrf=False)
    def operation_inbound_create(self, **kw):
        user = request.env.user.sudo()
        project_records = user.stock_operation_project_line_ids
        payload, payload_error = self.get_request_values(kw) if request.httprequest.method == 'POST' else (kw, '')
        project_id = payload.get('project_id', '')
        active_project_record = project_records.filtered(lambda project: str(project.id) == str(project_id))[:1]
        product_records = request.env['product.product'].sudo().search([('categ_id', '=', active_project_record.category.id)]) if active_project_record and active_project_record.category else request.env['product.product'].sudo().browse()
        form_values = {'reference': '', 'date': fields.Date.context_today(request.env.user), 'a_date': '', 'project_id': project_id or None, 'bl_no': '', 'cntr_no': '', 'is_adr': True, 'remark': '', 'lines': []}
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
            missing_fields = [label for label, field_value in [
                (_('Reference'), str(payload.get('reference') or '').strip()), (_('Order Date'), payload.get('date')),
                (_('Arrival Date'), payload.get('a_date')), (_('Container Number'), str(payload.get('cntr_no') or '').strip()),
            ] if not field_value]
            if missing_fields:
                values['error'] = _('The following fields are required: %s') % ', '.join(missing_fields)
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            try:
                fields.Date.to_date(payload['date'])
                fields.Date.to_date(payload['a_date'])
            except (TypeError, ValueError):
                values['error'] = _('Order date and arrival date must be valid dates.')
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
                    'is_adr': payload.get('is_adr', True), 'remark': str(payload.get('remark') or '').strip(), 'creation_source': 'portal', 'inbound_order_product_ids': lines,
                })
            except (UserError, ValidationError) as error:
                values['error'] = error.args[0]
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            return request.redirect('/my/operation/inbounds/%s' % order.id)
        return request.render("stock_operation_portal.portal_operation_inbound_form", values)

    @http.route(["/my/operation/inbounds/<int:order_id>/edit"], type="http", auth="user", website=True, methods=["GET", "POST"], csrf=False)
    def operation_inbound_edit(self, order_id, **kw):
        inbound_model = request.env['world.depot.inbound.order']
        order_sudo = inbound_model.sudo().search([('id', '=', order_id), ('state', '=', 'new'), ('stock_operation_portal_confirmed', '=', False)] + self.get_stock_operation_project_domain(), limit=1)
        if not order_sudo:
            return request.not_found()
        payload, payload_error = self.get_request_values(kw) if request.httprequest.method == 'POST' else (kw, '')
        active_project_record = order_sudo.project
        product_records = request.env['product.product'].sudo().search([('categ_id', '=', active_project_record.category.id)]) if active_project_record and active_project_record.category else request.env['product.product'].sudo()
        edit_lines = []
        for line in order_sudo.inbound_order_product_ids:
            edit_lines.append({
                'id': line.id,
                'pallet_no': line.pallet_no or '',
                'pallets': line.pallets or 0.0,
                'pallet_type': line.pallet_type or '',
                'remark': line.remark or '',
                'products': [{
                    'id': product_line.id,
                    'product_id': product_line.product_id.id,
                    'product_name': portal_product_name(product_line.product_id),
                    'quantity': product_line.quantity or 0.0,
                    'gross_weight': getattr(product_line, 'stock_operation_gross_weight', 0.0) or 0.0,
                    'net_weight': getattr(product_line, 'stock_operation_net_weight', 0.0) or 0.0,
                    'remark': product_line.remark or '',
                    'un_code': product_line.product_id.un_code or '',
                } for product_line in line.inbound_order_product_pallet_ids],
            })
        state = 'portal_confirmed' if order_sudo.state == 'new' and order_sudo.stock_operation_portal_confirmed else order_sudo.state
        order_data = {
            'id': order_sudo.id,
            'type': order_sudo.type or 'inbound',
            'state': state,
            'status': order_sudo.status or '',
            'date': fields.Date.to_string(order_sudo.date) if order_sudo.date else '',
            'a_date': fields.Date.to_string(order_sudo.a_date) if order_sudo.a_date else '',
            'reference': order_sudo.reference or '',
            'bl_no': order_sudo.bl_no or '',
            'container_no': order_sudo.cntr_no or '',
            'is_adr': bool(order_sudo.is_adr),
            'remark': order_sudo.remark or '',
            'project_id': active_project_record.id if active_project_record else None,
            'project_name': active_project_record.name if active_project_record else '',
            'lines': edit_lines,
        }
        values = self._prepare_page_values("operation_inbound_edit", "Edit Inbound Order")
        values.update({
            'order': order_data,
            'active_project': {'id': active_project_record.id, 'name': active_project_record.name or ''} if active_project_record else None,
            'products': [{'id': product.id, 'default_name': product.display_name or product.name or ''} for product in product_records],
            'detail_rows': inbound_model.get_inbound_detail_grouped(order_id),
            'attachment_rows': inbound_model.get_inbound_attachments(order_id),
        })
        if request.httprequest.method == 'POST':
            if payload_error:
                values['error'] = payload_error
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            reference = str((payload.get('reference') or '') if 'reference' in payload else order_sudo.reference or '').strip()
            order_date = payload.get('date', fields.Date.to_string(order_sudo.date) if order_sudo.date else '')
            arrival_date = payload.get('a_date', fields.Date.to_string(order_sudo.a_date) if order_sudo.a_date else '')
            container_no = str((payload.get('cntr_no') or '') if 'cntr_no' in payload else order_sudo.cntr_no or '').strip()
            missing_fields = [label for label, field_value in [
                (_('Reference'), reference), (_('Order Date'), order_date), (_('Arrival Date'), arrival_date), (_('Container Number'), container_no),
            ] if not field_value]
            if missing_fields:
                values['error'] = _('The following fields are required: %s') % ', '.join(missing_fields)
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            if 'is_adr' in payload and not isinstance(payload['is_adr'], bool):
                values['error'] = _('is_adr must be a boolean.')
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            if 'is_scan_sn' in payload and not isinstance(payload['is_scan_sn'], bool):
                values['error'] = _('is_scan_sn must be a boolean.')
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            deleted_line_ids = payload.get('deleted_line_ids', [])
            if not isinstance(deleted_line_ids, list):
                values['error'] = _('deleted_line_ids must be a list.')
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            deleted_line_id_set = set()
            deleted_line_commands = []
            for deleted_line_id in deleted_line_ids:
                if not str(deleted_line_id).isdigit() or int(deleted_line_id) in deleted_line_id_set:
                    values['error'] = _('deleted_line_ids must contain unique pallet line ids.')
                    return request.render("stock_operation_portal.portal_operation_inbound_form", values)
                deleted_line = order_sudo.inbound_order_product_ids.filtered(lambda line: line.id == int(deleted_line_id))[:1]
                if not deleted_line:
                    values['error'] = _('Every deleted pallet line id must belong to the current inbound order.')
                    return request.render("stock_operation_portal.portal_operation_inbound_form", values)
                deleted_line_id_set.add(deleted_line.id)
                deleted_product_commands = [(2, product_line.id, 0) for product_line in deleted_line.inbound_order_product_pallet_ids]
                if deleted_product_commands:
                    deleted_line_commands.append((1, deleted_line.id, {'inbound_order_product_pallet_ids': deleted_product_commands}))
                deleted_line_commands.append((2, deleted_line.id, 0))
            write_values = {'reference': reference, 'date': order_date, 'a_date': arrival_date}
            for field_name in ('bl_no', 'cntr_no', 'remark'):
                if field_name in payload:
                    write_values[field_name] = str(payload[field_name] or '').strip()
            if 'is_adr' in payload:
                write_values['is_adr'] = payload['is_adr']
            if 'is_scan_sn' in payload:
                write_values['is_scan_sn'] = payload['is_scan_sn']
            lines = []
            if 'lines' in payload:
                lines, error = self.get_inbound_line_values(payload.get('lines'), order_sudo.project, order_sudo, deleted_line_id_set)
                if error:
                    values['error'] = error
                    return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            if 'lines' in payload or deleted_line_commands:
                write_values['inbound_order_product_ids'] = lines + deleted_line_commands
            try:
                inbound_model.browse(order_sudo.id).write(write_values)
            except (UserError, ValidationError) as error:
                values['error'] = error.args[0]
                return request.render("stock_operation_portal.portal_operation_inbound_form", values)
            return request.redirect('/my/operation/inbounds/%s' % order_sudo.id)
        return request.render("stock_operation_portal.portal_operation_inbound_form", values)

    @http.route(["/my/operation/inbounds/<int:order_id>"], type="http", auth="user", website=True)
    def operation_inbound_detail(self, order_id, **kw):
        inbound_env = request.env["world.depot.inbound.order"]
        order_record = inbound_env.get_inbound_order(order_id)
        if not order_record:
            return request.not_found()
        state = 'portal_confirmed' if order_record.state == 'new' and order_record.stock_operation_portal_confirmed else order_record.state
        order = {
            'id': order_record.id,
            'type': order_record.type or 'inbound',
            'state': state,
            'status': order_record.status or '',
            'date': fields.Date.to_string(order_record.date) if order_record.date else '',
            'a_date': fields.Date.to_string(order_record.a_date) if order_record.a_date else '',
            'reference': order_record.reference or '',
            'bl_no': order_record.bl_no or '',
            'container_no': order_record.cntr_no or '',
            'is_adr': bool(order_record.is_adr),
            'remark': order_record.remark or '',
            'project_id': order_record.project.id if order_record.project else None,
            'project_name': order_record.project.name if order_record.project else '',
        }
        values = self._prepare_page_values("operation_inbound_detail", "Inbound Order Detail")
        values.update({'order': order, 'detail_rows': inbound_env.get_inbound_detail_grouped(order_id), 'attachment_rows': inbound_env.get_inbound_attachments(order_id)})
        return request.render("stock_operation_portal.portal_operation_inbound_detail", values)

    @http.route(["/my/operation/inbounds/<int:order_id>/cancel"], type="http", auth="user", website=True, methods=["POST"], csrf=False)
    def operation_inbound_cancel(self, order_id, **kw):
        inbound_model = request.env['world.depot.inbound.order']
        order_sudo = inbound_model.sudo().search([('id', '=', order_id), ('state', 'in', ['new', 'confirm']), ('stock_operation_portal_confirmed', '=', False)] + self.get_stock_operation_project_domain(), limit=1)
        if not order_sudo:
            return request.not_found()
        if self.get_inbound_picking(order_sudo.id):
            raise UserError(_('Cannot cancel an inbound order after a receipt has been created.'))
        inbound_model.browse(order_sudo.id).action_cancel()
        return request.redirect('/my/operation/inbounds/%s' % order_sudo.id)

    @http.route(["/my/operation/inbounds/<int:order_id>/portal_confirm"], type="http", auth="user", website=True, methods=["POST"])
    def operation_inbound_portal_confirm(self, order_id, **kw):
        inbound_model = request.env['world.depot.inbound.order']
        order_sudo = inbound_model.sudo().search([('id', '=', order_id), ('state', '=', 'new'), ('stock_operation_portal_confirmed', '=', False)] + self.get_stock_operation_project_domain(), limit=1)
        if not order_sudo:
            return request.not_found()
        inbound_model.browse(order_sudo.id).write({
            'stock_operation_portal_confirmed': True, 'stock_operation_portal_confirm_user_id': request.env.user.id,
            'stock_operation_portal_confirm_time': fields.Datetime.now(),
        })
        return request.redirect('/my/operation/inbounds/%s' % order_sudo.id)

    @http.route(["/my/operation/inbounds/<int:order_id>/portal_unconfirm"], type="http", auth="user", website=True, methods=["POST"], csrf=False)
    def operation_inbound_portal_unconfirm(self, order_id, **kw):
        inbound_model = request.env['world.depot.inbound.order']
        order_sudo = inbound_model.sudo().search([('id', '=', order_id), ('state', 'in', ['new', 'confirm']), ('stock_operation_portal_confirmed', '=', True)] + self.get_stock_operation_project_domain(), limit=1)
        if not order_sudo:
            return request.not_found()
        inbound_model.browse(order_sudo.id).write({
            'stock_operation_portal_confirmed': False, 'stock_operation_portal_confirm_user_id': False,
            'stock_operation_portal_confirm_time': False,
        })
        return request.redirect('/my/operation/inbounds/%s' % order_sudo.id)
