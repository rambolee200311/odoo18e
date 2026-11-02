# -*- coding: utf-8 -*-

from odoo import _, fields, http
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from ..models.utils import portal_product_name
from .portal import StockOperationPortal


class StockOperationOutboundPortal(StockOperationPortal):

    def get_outbound_line_values(self, line_values, project, order=None):
        if not isinstance(line_values, list):
            return [], _('The lines field must be a list.')
        lines = []
        product_env = request.env['product.product'].sudo()
        package_env = request.env['stock.quant.package'].sudo()
        inbound_pallet_env = request.env['world.depot.inbound.order.product'].sudo()
        lot_env = request.env['stock.lot'].sudo()
        quant_env = request.env['stock.quant'].sudo()
        for line_value in line_values:
            if not isinstance(line_value, dict):
                return [], _('Every outbound line must be a JSON object.')
            line_id = line_value.get('id')
            existing_line = order.outbound_order_product_ids.filtered(lambda line: line.id == int(line_id))[:1] if order and line_id not in (None, '') and str(line_id).isdigit() else order.outbound_order_product_ids[:0] if order else None
            if line_id not in (None, '') and not existing_line:
                return [], _('Every product line id must belong to the current outbound order.')
            product_id = line_value.get('product_id') if 'product_id' in line_value else existing_line.product_id.id if existing_line else False
            product = product_env.search([('id', '=', product_id), ('categ_id', '=', project.category.id)], limit=1)
            try:
                pallets = float(line_value.get('pallets') if 'pallets' in line_value else (existing_line.pallets if existing_line else 1))
                quantity = float(line_value.get('quantity') if 'quantity' in line_value else (existing_line.quantity if existing_line else 0))
            except (TypeError, ValueError):
                return [], _('Pallets and quantity must be valid numbers.')
            if not product or pallets <= 0 or quantity <= 0:
                return [], _('Every product line must use an allowed product with positive pallets and quantity.')
            is_lot = line_value.get('is_lot') if 'is_lot' in line_value else existing_line.is_lot == 'Y' if existing_line else False
            if not isinstance(is_lot, bool):
                return [], _('is_lot must be a boolean.')
            serial_number = str((line_value.get('serial_number') or '') if 'serial_number' in line_value else (existing_line.serial_numbers if existing_line else '') or '').strip()
            lot_value = line_value.get('lot_id') if 'lot_id' in line_value else False
            lot = lot_env.browse()
            if lot_value not in (None, ''):
                if not str(lot_value).isdigit():
                    return [], _('lot_id must be a valid lot id.')
                lot = lot_env.search([('id', '=', int(lot_value)), ('product_id', '=', product.id)], limit=1)
                if not lot:
                    return [], _('The selected lot must belong to the selected product.')
            elif existing_line and is_lot and existing_line.lot_name:
                lot = lot_env.search([('name', '=', existing_line.lot_name), ('product_id', '=', product.id)], limit=1)
            stock_lot = lot
            if is_lot:
                if product.tracking != 'lot' or not lot or serial_number:
                    return [], _('Lot-tracked products require a lot and cannot use a serial number.')
            elif serial_number:
                if product.tracking != 'serial' or lot or quantity != 1:
                    return [], _('Serial-tracked products require one serial number, no lot, and quantity 1.')
                stock_lot = lot_env.search([('name', '=', serial_number), ('product_id', '=', product.id)], limit=1)
                if not stock_lot:
                    return [], _('The selected serial number must belong to the selected product.')
            elif product.tracking == 'lot':
                return [], _('Lot-tracked products require a lot.')
            elif product.tracking == 'serial':
                return [], _('Serial-tracked products require a serial number.')
            elif lot:
                return [], _('Untracked products cannot use a lot.')
            pallet_value = line_value.get('pallet_id') if 'pallet_id' in line_value else existing_line.package_id.id if existing_line and existing_line.package_id else False
            package = package_env.browse()
            pallet_no = ''
            if pallet_value not in (None, ''):
                if not str(pallet_value).isdigit():
                    return [], _('pallet_id must be a valid pallet id.')
                package = package_env.search([('id', '=', int(pallet_value))], limit=1)
                inbound_pallet = inbound_pallet_env.search([('package_id', '=', package.id), ('project', '=', project.id), ('inbound_order_id.state', '!=', 'cancel')], order='id desc', limit=1)
                if not package or not inbound_pallet:
                    return [], _('The selected pallet does not belong to the current project.')
                quant_domain = [('package_id', '=', package.id), ('product_id', '=', product.id), ('location_id.usage', '=', 'internal'), ('quantity', '>', 0)]
                if stock_lot:
                    quant_domain.append(('lot_id', '=', stock_lot.id))
                available_quantity = sum((quant.quantity or 0.0) - (quant.reserved_quantity or 0.0) for quant in quant_env.search(quant_domain))
                if available_quantity < quantity:
                    return [], _('The selected pallet does not have enough available stock.')
                pallet_no = inbound_pallet.pallet_no or package.name or package.barcode or ''
            elif existing_line and 'pallet_id' not in line_value:
                pallet_no = existing_line.pallet_no or ''
            line_data = {
                'product_id': product.id,
                'pallets': pallets,
                'quantity': quantity,
                'package_id': package.id or False,
                'pallet_no': pallet_no,
                'is_lot': 'Y' if is_lot else 'N',
                'lot_name': lot.name if is_lot else False,
                'serial_numbers': serial_number or False,
                'pallet_type': str((line_value.get('pallet_type') or '') if 'pallet_type' in line_value else (existing_line.pallet_type if existing_line else '') or '').strip(),
                'cntr_no': str((line_value.get('container_no') or '') if 'container_no' in line_value else (existing_line.cntr_no if existing_line else '') or '').strip(),
                'pallet_prefix_code': str((line_value.get('pallet_prefix_code') or '') if 'pallet_prefix_code' in line_value else (existing_line.pallet_prefix_code if existing_line else '') or '').strip(),
                'remark': str((line_value.get('remark') or '') if 'remark' in line_value else (existing_line.remark if existing_line else '') or '').strip(),
            }
            if not existing_line:
                line_data['creation_source'] = 'portal'
            lines.append((1, existing_line.id, line_data) if existing_line else (0, 0, line_data))
        return lines, _('Add at least one product line.') if not lines else ''

    def get_outbound_picking(self, order_id):
        return request.env['stock.picking'].sudo().search([('outbound_order_id', '=', order_id), ('state', '!=', 'cancel')], limit=1)

    @http.route(['/my/operation/outbounds/available-pallets'], type='http', auth='user', website=True, methods=['GET'])
    def operation_outbound_available_pallets(self, **kw):
        project_id = kw.get('project_id')
        product_id = kw.get('product_id')
        lot_id = kw.get('lot_id')
        serial_number = str(kw.get('serial_number') or '').strip()
        if lot_id not in (None, '') and serial_number:
            return request.make_json_response({'pallets': [], 'error': _('lot_id and serial_number cannot be used together.')})
        user = request.env.user.sudo()
        project = user.stock_operation_project_line_ids.filtered(lambda item: str(item.id) == str(project_id))[:1]
        product = request.env['product.product'].sudo().search([('id', '=', product_id), ('categ_id', '=', project.category.id)], limit=1) if project and project.category else request.env['product.product'].sudo().browse()
        if not project or not product:
            return request.make_json_response({'pallets': []})
        lot_env = request.env['stock.lot'].sudo()
        stock_lot = lot_env.browse()
        if lot_id not in (None, ''):
            if not str(lot_id).isdigit():
                return request.make_json_response({'pallets': [], 'error': _('lot_id must be a valid lot id.')})
            stock_lot = lot_env.search([('id', '=', int(lot_id)), ('product_id', '=', product.id)], limit=1)
        elif serial_number:
            stock_lot = lot_env.search([('name', '=', serial_number), ('product_id', '=', product.id)], limit=1)
        if (lot_id not in (None, '') or serial_number) and not stock_lot:
            return request.make_json_response({'pallets': []})
        quant_domain = [('product_id', '=', product.id), ('package_id', '!=', False), ('location_id.usage', '=', 'internal'), ('quantity', '>', 0)]
        if stock_lot:
            quant_domain.append(('lot_id', '=', stock_lot.id))
        quants = request.env['stock.quant'].sudo().search(quant_domain)
        package_ids = quants.mapped('package_id').ids
        if not package_ids:
            return request.make_json_response({'pallets': []})
        inbound_pallets = request.env['world.depot.inbound.order.product'].sudo().search([('package_id', 'in', package_ids), ('project', '=', project.id), ('inbound_order_id.state', '!=', 'cancel')], order='id desc')
        pallet_no_by_package_id = {}
        for inbound_pallet in inbound_pallets:
            pallet_no_by_package_id.setdefault(inbound_pallet.package_id.id, inbound_pallet.pallet_no or inbound_pallet.package_id.name or inbound_pallet.package_id.barcode or '')
        available_by_package_id = {}
        for quant in quants:
            if quant.package_id.id not in pallet_no_by_package_id:
                continue
            available_by_package_id[quant.package_id.id] = available_by_package_id.get(quant.package_id.id, 0.0) + (quant.quantity or 0.0) - (quant.reserved_quantity or 0.0)
        packages = request.env['stock.quant.package'].sudo().search([('id', 'in', [package_id for package_id, quantity in available_by_package_id.items() if quantity > 0])], order='name, id')
        return request.make_json_response({'pallets': [{'pallet_id': package.id, 'pallet_no': pallet_no_by_package_id[package.id], 'available_quantity': available_by_package_id[package.id]} for package in packages]})

    @http.route(["/my/operation/outbounds", "/my/operation/outbounds/page/<int:page>"], type="http", auth="user", website=True)
    def operation_outbounds_page(self, page=1, **kw):
        filters = self._filter_values(kw, ["reference", "bl_no", "container_no", "state", "date_from", "date_to"])
        values = self._prepare_page_values("operation_outbounds", "Outbound Orders", filters)
        domain = self.get_stock_operation_project_domain()
        if filters['reference']:
            domain += ['|', ('reference', 'ilike', filters['reference']), ('billno', 'ilike', filters['reference'])]
        if filters['state'] == 'new':
            domain.extend([('state', '=', 'new'), ('stock_operation_portal_confirmed', '=', False)])
        elif filters['state'] == 'portal_confirmed':
            domain.extend([('state', '=', 'new'), ('stock_operation_portal_confirmed', '=', True)])
        elif filters['state']:
            domain.append(('state', '=', filters['state']))
        if filters['date_from']:
            domain.append(('date', '>=', filters['date_from']))
        if filters['date_to']:
            domain.append(('date', '<=', filters['date_to']))
        outbound_model = request.env['world.depot.outbound.order'].sudo()
        shipping_filters = bool(filters['bl_no'] or filters['container_no'])
        if shipping_filters:
            orders = outbound_model.search(domain, order='id desc')
            shipping_by_order = outbound_model.get_outbound_shipping_map(orders)
            matched_order_ids = set()
            for order in orders:
                shipping = shipping_by_order.get(order.id, {'containers': set(), 'bls': set()})
                containers = set(filter(None, order.outbound_order_product_ids.mapped('cntr_no'))) | shipping['containers']
                if filters['container_no'] and not any(filters['container_no'].lower() in container.lower() for container in containers):
                    continue
                if filters['bl_no'] and not any(filters['bl_no'].lower() in bl_no.lower() for bl_no in shipping['bls']):
                    continue
                matched_order_ids.add(order.id)
            total = len(matched_order_ids)
            pager = portal_pager(url='/my/operation/outbounds', url_args=filters, total=total, page=page, step=20)
            orders = orders.filtered(lambda order: order.id in matched_order_ids)[pager['offset']:pager['offset'] + 20]
        else:
            total = outbound_model.search_count(domain)
            pager = portal_pager(url='/my/operation/outbounds', url_args=filters, total=total, page=page, step=20)
            orders = outbound_model.search(domain, order='id desc', offset=pager['offset'], limit=20)
            shipping_by_order = outbound_model.get_outbound_shipping_map(orders)
        rows = []
        for order in orders:
            shipping = shipping_by_order.get(order.id, {'containers': set(), 'bls': set()})
            containers = set(filter(None, order.outbound_order_product_ids.mapped('cntr_no'))) | shipping['containers']
            state = 'portal_confirmed' if order.state == 'new' and order.stock_operation_portal_confirmed else order.state
            rows.append({
                'id': order.id,
                'outbound_no': order.billno or order.reference or '',
                'reference': order.reference or '',
                'bl_no': ', '.join(sorted(shipping['bls'])),
                'container_no': ', '.join(sorted(containers)),
                'expected_date': fields.Date.to_string(order.p_date or order.date) if order.p_date or order.date else '',
                'state': state,
                'portal_confirmed': order.stock_operation_portal_confirmed,
                'total_quantity': sum(order.outbound_order_product_ids.mapped('quantity')),
            })
        values.update({'pager': pager, 'rows': rows})
        return request.render("stock_operation_portal.portal_operation_outbounds", values)

    @http.route(["/my/operation/outbounds/create"], type="http", auth="user", website=True, methods=["GET", "POST"])
    def operation_outbound_create(self, **kw):
        user = request.env.user.sudo()
        project_records = user.stock_operation_project_line_ids
        payload, payload_error = self.get_request_values(kw) if request.httprequest.method == 'POST' else (kw, '')
        project_id = payload.get('project_id', '')
        active_project_record = project_records.filtered(lambda project: str(project.id) == str(project_id))[:1]
        product_records = request.env['product.product'].sudo().search([('categ_id', '=', active_project_record.category.id)]) if active_project_record and active_project_record.category else request.env['product.product'].sudo().browse()
        form_values = {'reference': '', 'date': '', 'p_date': '', 'o_date': '', 'project_id': project_id or None, 'remark': '', 'lines': []}
        form_values.update(payload)
        values = self._prepare_page_values("operation_outbound_create", "Create Outbound Order")
        values.update({
            'projects': [{'id': project.id, 'name': project.name or ''} for project in project_records],
            'active_project': {'id': active_project_record.id, 'name': active_project_record.name or ''} if active_project_record else None,
            'products': [{'id': product.id, 'default_name': product.display_name or product.name or ''} for product in product_records],
            'form_values': form_values,
            'attachment_rows': [],
        })
        if not project_records:
            values['error'] = _('Your portal user is not assigned Stock Operation projects. Please contact an administrator.')
            return request.render("stock_operation_portal.portal_operation_outbound_form", values)
        if request.httprequest.method == 'POST':
            if payload_error:
                values['error'] = payload_error
                return request.render("stock_operation_portal.portal_operation_outbound_form", values)
            if not active_project_record:
                values['error'] = _('Please select an available project.')
                return request.render("stock_operation_portal.portal_operation_outbound_form", values)
            if not active_project_record.category:
                values['error'] = _('The selected project has no product category.')
                return request.render("stock_operation_portal.portal_operation_outbound_form", values)
            if not str(payload.get('reference') or '').strip() or not payload.get('date'):
                values['error'] = _('Reference and order date are required.')
                return request.render("stock_operation_portal.portal_operation_outbound_form", values)
            lines, error = self.get_outbound_line_values(payload.get('lines'), active_project_record)
            if error:
                values['error'] = error
                return request.render("stock_operation_portal.portal_operation_outbound_form", values)
            try:
                order = request.env['world.depot.outbound.order'].create({
                    'type': 'outbound', 'project': active_project_record.id, 'reference': str(payload['reference']).strip(), 'date': payload['date'],
                    'p_date': payload.get('p_date') or False, 'o_date': payload.get('o_date') or False,
                    'remark': str(payload.get('remark') or '').strip(), 'creation_source': 'portal', 'outbound_order_product_ids': lines,
                })
            except (UserError, ValidationError) as error:
                values['error'] = error.args[0]
                return request.render("stock_operation_portal.portal_operation_outbound_form", values)
            return request.redirect('/my/operation/outbounds/%s' % order.id)
        return request.render("stock_operation_portal.portal_operation_outbound_form", values)

    @http.route(["/my/operation/outbounds/<int:order_id>/edit"], type="http", auth="user", website=True, methods=["GET", "POST"])
    def operation_outbound_edit(self, order_id, **kw):
        outbound_model = request.env['world.depot.outbound.order']
        order_sudo = outbound_model.sudo().search([('id', '=', order_id), ('state', '=', 'new'), ('stock_operation_portal_confirmed', '=', False)] + self.get_stock_operation_project_domain(), limit=1)
        if not order_sudo:
            return request.not_found()
        payload, payload_error = self.get_request_values(kw) if request.httprequest.method == 'POST' else (kw, '')
        active_project_record = order_sudo.project
        product_records = request.env['product.product'].sudo().search([('categ_id', '=', active_project_record.category.id)]) if active_project_record and active_project_record.category else request.env['product.product'].sudo().browse()
        lot_names = list({line.lot_name for line in order_sudo.outbound_order_product_ids if line.is_lot == 'Y' and line.lot_name})
        lot_id_by_key = {}
        if lot_names:
            lot_records = request.env['stock.lot'].sudo().search([('product_id', 'in', order_sudo.outbound_order_product_ids.mapped('product_id').ids), ('name', 'in', lot_names)])
            lot_id_by_key = {(lot.product_id.id, lot.name): lot.id for lot in lot_records}
        order_data = {
            'id': order_sudo.id,
            'type': order_sudo.type or 'outbound',
            'state': 'portal_confirmed' if order_sudo.stock_operation_portal_confirmed else order_sudo.state,
            'status': order_sudo.status or '',
            'date': fields.Date.to_string(order_sudo.date) if order_sudo.date else '',
            'p_date': fields.Date.to_string(order_sudo.p_date) if order_sudo.p_date else '',
            'o_date': fields.Date.to_string(order_sudo.o_date) if order_sudo.o_date else '',
            'reference': order_sudo.reference or '',
            'remark': order_sudo.remark or '',
            'project_id': active_project_record.id if active_project_record else None,
            'project_name': active_project_record.name if active_project_record else '',
            'lines': [{
                'id': line.id,
                'product_id': line.product_id.id,
                'product_name': portal_product_name(line.product_id),
                'quantity': line.quantity or 0.0,
                'pallets': line.pallets or 0.0,
                'pallet_id': line.package_id.id or None,
                'pallet_no': line.pallet_no or '',
                'pallet_type': line.pallet_type or '',
                'container_no': line.cntr_no or '',
                'pallet_prefix_code': line.pallet_prefix_code or '',
                'is_lot': line.is_lot == 'Y',
                'lot_id': lot_id_by_key.get((line.product_id.id, line.lot_name)),
                'serial_number': line.serial_numbers or '',
                'remark': line.remark or '',
                'un_code': line.product_id.un_code or '',
            } for line in order_sudo.outbound_order_product_ids],
        }
        values = self._prepare_page_values("operation_outbound_edit", "Edit Outbound Order")
        values.update({
            'order': order_data,
            'active_project': {'id': active_project_record.id, 'name': active_project_record.name or ''} if active_project_record else None,
            'products': [{'id': product.id, 'default_name': product.display_name or product.name or ''} for product in product_records],
            'detail_rows': outbound_model.get_outbound_detail_grouped(order_id),
            'attachment_rows': outbound_model.get_outbound_attachments(order_id),
        })
        if request.httprequest.method == 'POST':
            if payload_error:
                values['error'] = payload_error
                return request.render("stock_operation_portal.portal_operation_outbound_form", values)
            reference = str((payload.get('reference') or '') if 'reference' in payload else order_sudo.reference or '').strip()
            order_date = payload.get('date', fields.Date.to_string(order_sudo.date) if order_sudo.date else '')
            if not reference or not order_date:
                values['error'] = _('Reference and order date are required.')
                return request.render("stock_operation_portal.portal_operation_outbound_form", values)
            write_values = {'reference': reference, 'date': order_date}
            for field_name in ('p_date', 'o_date'):
                if field_name in payload:
                    write_values[field_name] = payload[field_name] or False
            if 'remark' in payload:
                write_values['remark'] = str(payload['remark'] or '').strip()
            if 'lines' in payload:
                lines, error = self.get_outbound_line_values(payload.get('lines'), order_sudo.project, order_sudo)
                if error:
                    values['error'] = error
                    return request.render("stock_operation_portal.portal_operation_outbound_form", values)
                write_values['outbound_order_product_ids'] = lines
            try:
                outbound_model.browse(order_sudo.id).write(write_values)
            except (UserError, ValidationError) as error:
                values['error'] = error.args[0]
                return request.render("stock_operation_portal.portal_operation_outbound_form", values)
            return request.redirect('/my/operation/outbounds/%s' % order_sudo.id)
        return request.render("stock_operation_portal.portal_operation_outbound_form", values)

    @http.route(["/my/operation/outbounds/<int:order_id>"], type="http", auth="user", website=True)
    def operation_outbound_detail(self, order_id, **kw):
        outbound_env = request.env['world.depot.outbound.order']
        order_record = outbound_env.get_outbound_order(order_id)
        if not order_record:
            return request.not_found()
        state = 'portal_confirmed' if order_record.state == 'new' and order_record.stock_operation_portal_confirmed else order_record.state
        values = self._prepare_page_values("operation_outbound_detail", "Outbound Order Detail")
        values.update({
            'order': {
                'id': order_record.id,
                'type': order_record.type or 'outbound',
                'state': state,
                'status': order_record.status or '',
                'date': fields.Date.to_string(order_record.date) if order_record.date else '',
                'p_date': fields.Date.to_string(order_record.p_date) if order_record.p_date else '',
                'o_date': fields.Date.to_string(order_record.o_date) if order_record.o_date else '',
                'reference': order_record.reference or '',
                'remark': order_record.remark or '',
                'project_id': order_record.project.id if order_record.project else None,
                'project_name': order_record.project.name if order_record.project else '',
            },
            'detail_rows': outbound_env.get_outbound_detail_grouped(order_id),
            'attachment_rows': outbound_env.get_outbound_attachments(order_id),
        })
        return request.render("stock_operation_portal.portal_operation_outbound_detail", values)

    @http.route(["/my/operation/outbounds/<int:order_id>/cancel"], type="http", auth="user", website=True, methods=["POST"])
    def operation_outbound_cancel(self, order_id, **kw):
        outbound_model = request.env['world.depot.outbound.order']
        order_sudo = outbound_model.sudo().search([('id', '=', order_id), ('state', 'in', ['new', 'confirm']), ('stock_operation_portal_confirmed', '=', False)] + self.get_stock_operation_project_domain(), limit=1)
        if not order_sudo:
            return request.not_found()
        if self.get_outbound_picking(order_sudo.id):
            raise UserError(_('Cannot cancel an outbound order after a picking has been created.'))
        outbound_model.browse(order_sudo.id).action_cancel()
        return request.redirect('/my/operation/outbounds/%s' % order_sudo.id)

    @http.route(["/my/operation/outbounds/<int:order_id>/portal_confirm"], type="http", auth="user", website=True, methods=["POST"])
    def operation_outbound_portal_confirm(self, order_id, **kw):
        outbound_model = request.env['world.depot.outbound.order']
        order_sudo = outbound_model.sudo().search([('id', '=', order_id), ('state', '=', 'new'), ('stock_operation_portal_confirmed', '=', False)] + self.get_stock_operation_project_domain(), limit=1)
        if not order_sudo:
            return request.not_found()
        outbound_model.browse(order_sudo.id).write({
            'stock_operation_portal_confirmed': True,
            'stock_operation_portal_confirm_user_id': request.env.user.id,
            'stock_operation_portal_confirm_time': fields.Datetime.now(),
        })
        return request.redirect('/my/operation/outbounds/%s' % order_sudo.id)

    @http.route(["/my/operation/outbounds/<int:order_id>/portal_unconfirm"], type="http", auth="user", website=True, methods=["POST"])
    def operation_outbound_portal_unconfirm(self, order_id, **kw):
        outbound_model = request.env['world.depot.outbound.order']
        order_sudo = outbound_model.sudo().search([('id', '=', order_id), ('state', 'in', ['new', 'confirm']), ('stock_operation_portal_confirmed', '=', True)] + self.get_stock_operation_project_domain(), limit=1)
        if not order_sudo:
            return request.not_found()
        outbound_model.browse(order_sudo.id).write({
            'stock_operation_portal_confirmed': False,
            'stock_operation_portal_confirm_user_id': False,
            'stock_operation_portal_confirm_time': False,
        })
        return request.redirect('/my/operation/outbounds/%s' % order_sudo.id)
