# -*- coding: utf-8 -*-

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class WarehouseValueAddScanService(models.AbstractModel):
    _inherit = 'stock.barcode.lite.scan.service'

    @api.model
    def get_vas_outbound_palletization(self, palletization_id):
        palletization_model = self.env['wd.vas.outbound.palletization']
        palletization_ids = palletization_model.sudo().search([('id', '=', palletization_id)], limit=1).ids
        palletization = palletization_model.browse(palletization_ids)
        if not palletization:
            raise UserError(_('Outbound palletization was not found.'))
        palletization.check_access_rights('read')
        palletization.check_access_rule('read')
        return palletization

    @api.model
    def get_vas_outbound_palletization_move_lines(self, palletization, source_package_id=False, product_id=False, lot_id=False):
        move_line_model = self.env['stock.move.line']
        domain = [('picking_id', 'in', palletization.picking_ids.ids), ('state', '!=', 'cancel'), ('quantity', '>', 0)]
        domain.append(('package_id', '=', source_package_id or False))
        if product_id:
            domain.append(('product_id', '=', product_id))
        if lot_id:
            domain.append(('lot_id', '=', lot_id))
        move_line_ids = move_line_model.sudo().search(domain, order='id').ids
        return move_line_model.browse(move_line_ids)

    @api.model
    def get_vas_outbound_palletization_remaining_quantity(self, palletization, move_line):
        allocated_quantity = sum(palletization.palletization_lines.filtered(lambda line: line.source_move_line_id == move_line).mapped('quantity'))
        return max(move_line.quantity - allocated_quantity, 0.0)

    @api.model
    def get_vas_outbound_palletization_available_move_lines(self, palletization, source_package_id=False, product_id=False, lot_id=False):
        return self.get_vas_outbound_palletization_move_lines(palletization, source_package_id, product_id, lot_id).filtered(lambda line: self.get_vas_outbound_palletization_remaining_quantity(palletization, line) > 0)

    @api.model
    def build_vas_outbound_palletization_result(self, success, message, next_step='scan_source', context=None):
        current = dict(context or {})
        current.setdefault('barcode', self.env.context.get('vas_outbound_palletization_barcode', False))
        palletization = self.env['wd.vas.outbound.palletization'].browse(self.env.context.get('vas_outbound_palletization_id'))
        return {'success': success, 'type': 'palletization', 'barcode': current.get('barcode', False), 'message': message, 'next_step': next_step, 'current': {'destination_package_id': current.get('destination_package_id', False), 'source_package_id': current.get('source_package_id', False), 'product_id': current.get('product_id', False), 'lot_id': current.get('lot_id', False), 'tracking_number': current.get('tracking_number', current.get('lot_name', False)), 'quantity': current.get('quantity', False)}, 'scan_state': self.get_vas_outbound_palletization_scan_data(palletization, current, message)}

    @api.model
    def get_vas_outbound_palletization_scan_state(self, palletization_id):
        palletization = self.get_vas_outbound_palletization(palletization_id)
        return self.with_context(vas_outbound_palletization_id=palletization.id).build_vas_outbound_palletization_result(True, _('Scan a destination transport pallet.'), 'scan_destination')

    @api.model
    def get_vas_outbound_palletization_scan_data(self, palletization, current, message):
        package_model = self.env['stock.quant.package']
        product_model = self.env['product.product']
        lot_model = self.env['stock.lot']
        source_package = package_model.browse(current.get('source_package_id'))
        destination_package = package_model.browse(current.get('destination_package_id'))
        product = product_model.browse(current.get('product_id'))
        lot = lot_model.browse(current.get('lot_id'))
        transport_pallets = {}
        assigned_quantity = 0.0
        for package in palletization.transport_pallet_ids.sorted('id'):
            transport_pallets[package.id] = {'id': package.id, 'name': package.display_name, 'barcode': package.barcode, 'product_lines': {}}
        for allocation in palletization.palletization_lines.sorted('id'):
            destination = allocation.destination_package_id
            pallet_data = transport_pallets.setdefault(destination.id, {'id': destination.id, 'name': destination.display_name, 'barcode': destination.barcode, 'product_lines': {}})
            product_data = pallet_data['product_lines'].setdefault(allocation.product_id.id, {'product_id': allocation.product_id.id, 'product_name': allocation.product_id.display_name, 'product_barcode': allocation.product_id.barcode, 'tracking': allocation.product_id.tracking, 'quantity': 0.0, 'source_allocation_lines': [], 'tracking_lines': []})
            allocation_data = {'id': allocation.id, 'source_package_id': allocation.source_package_id.id, 'source_pallet_name': allocation.source_package_id.display_name, 'source_barcode': allocation.source_package_id.barcode, 'lot_id': allocation.lot_id.id, 'lot_name': allocation.lot_id.name or '', 'quantity': allocation.quantity}
            product_data['quantity'] += allocation.quantity
            product_data['source_allocation_lines'].append(allocation_data)
            if allocation.product_id.tracking in ('lot', 'serial'):
                product_data['tracking_lines'].append(allocation_data)
            assigned_quantity += allocation.quantity
        transport_pallet_data = []
        for pallet_data in transport_pallets.values():
            pallet_data['product_lines'] = list(pallet_data['product_lines'].values())
            transport_pallet_data.append(pallet_data)
        move_lines = palletization.get_picking_move_lines() if palletization else self.env['stock.move.line']
        total_quantity = sum(move_lines.mapped('quantity'))
        unassigned_lines = []
        for move_line in move_lines:
            remaining_quantity = self.get_vas_outbound_palletization_remaining_quantity(palletization, move_line)
            if remaining_quantity > 0:
                unassigned_lines.append({'id': move_line.id, 'source_package_id': move_line.package_id.id, 'source_barcode': move_line.package_id.barcode, 'product_id': move_line.product_id.id, 'product_name': move_line.product_id.display_name, 'lot': move_line.lot_id.name or '', 'quantity': remaining_quantity})
        return {'palletization': {'id': palletization.id, 'name': palletization.name, 'state': palletization.state} if palletization else False, 'current_destination_pallet': {'id': destination_package.id, 'name': destination_package.display_name, 'barcode': destination_package.barcode} if destination_package else False, 'current_source_pallet': {'id': source_package.id, 'name': source_package.display_name, 'barcode': source_package.barcode} if source_package else False, 'current_product': {'id': product.id, 'name': product.display_name, 'barcode': product.barcode, 'tracking': product.tracking} if product else False, 'current_lot': {'id': lot.id, 'name': lot.name} if lot else False, 'transport_pallets': transport_pallet_data, 'unassigned_lines': unassigned_lines, 'summary': {'total_quantity': total_quantity, 'assigned_quantity': assigned_quantity, 'unassigned_quantity': total_quantity - assigned_quantity}, 'last_scan': {'barcode': current.get('barcode', False), 'message': message}}

    @api.model
    def update_vas_outbound_palletization_line(self, palletization_id, line_id, quantity, handling_type, destination_code=False, destination_package_id=False):
        palletization = self.get_vas_outbound_palletization(palletization_id)
        self = self.with_context(vas_outbound_palletization_id=palletization.id, vas_outbound_palletization_barcode=destination_code)
        line_model = self.env['wd.vas.outbound.palletization.line']
        line_ids = line_model.sudo().search([('id', '=', line_id), ('palletization_id', '=', palletization.id)], limit=1).ids
        line = line_model.browse(line_ids)
        if not line:
            return self.build_vas_outbound_palletization_result(False, _('Palletization allocation was not found.'))
        line.check_access_rights('write')
        line.check_access_rule('write')
        destination_package = self.get_outgoing_package_from_barcode(destination_code) if destination_code else self.env['stock.quant.package'].browse(self.env['stock.quant.package'].sudo().search([('id', '=', destination_package_id)], limit=1).ids)
        scan_quantity = self.parse_outgoing_quantity(quantity)
        if not scan_quantity or not destination_package or handling_type not in ('palletize', 'direct_outbound'):
            return self.build_vas_outbound_palletization_result(False, _('Enter a valid quantity, handling type, and destination pallet.'))
        try:
            line.write({'quantity': scan_quantity, 'destination_package_id': destination_package.id, 'handling_type': handling_type})
        except UserError as error:
            return self.build_vas_outbound_palletization_result(False, str(error))
        return self.build_vas_outbound_palletization_result(True, _('Palletization allocation updated.'), 'scan_source', {'destination_package_id': line.destination_package_id.id, 'source_package_id': line.source_package_id.id, 'product_id': line.product_id.id, 'lot_id': line.lot_id.id, 'lot_name': line.lot_id.name or False, 'quantity': line.quantity})

    @api.model
    def remove_vas_outbound_palletization_allocations(self, palletization_id, destination_package_id, allocation_line_ids):
        palletization = self.get_vas_outbound_palletization(palletization_id)
        self = self.with_context(vas_outbound_palletization_id=palletization.id)
        line_model = self.env['wd.vas.outbound.palletization.line']
        package_model = self.env['stock.quant.package']
        line_ids = sorted(set(allocation_line_ids or [])) if isinstance(allocation_line_ids, (list, tuple)) else []
        destination_package_ids = package_model.sudo().search([('id', '=', destination_package_id), ('vas_outbound_palletization_id', '=', palletization.id)], limit=1).ids
        destination_package = package_model.browse(destination_package_ids)
        if not destination_package:
            return self.build_vas_outbound_palletization_result(False, _('Destination transport pallet was not found for this palletization.'))
        if not line_ids:
            return self.build_vas_outbound_palletization_result(False, _('Choose at least one palletization allocation.'))
        allocations = line_model.browse(line_model.sudo().search([('id', 'in', line_ids), ('palletization_id', '=', palletization.id), ('destination_package_id', '=', destination_package.id)], order='id').ids)
        if len(allocations) != len(line_ids):
            return self.build_vas_outbound_palletization_result(False, _('Some palletization allocations do not belong to this destination transport pallet.'))
        allocations.check_access_rights('unlink')
        allocations.check_access_rule('unlink')
        source_packages = allocations.mapped('source_package_id')
        try:
            allocations.unlink()
        except UserError as error:
            return self.build_vas_outbound_palletization_result(False, str(error))
        return self.build_vas_outbound_palletization_result(True, _('Palletization allocations removed.'), 'scan_source', {'destination_package_id': destination_package.id, 'source_package_id': source_packages.id if len(source_packages) == 1 else False})

    @api.model
    def action_validate_vas_outbound_palletization(self, palletization_id):
        palletization = self.get_vas_outbound_palletization(palletization_id)
        self = self.with_context(vas_outbound_palletization_id=palletization.id)
        palletization.check_access_rights('write')
        palletization.check_access_rule('write')
        try:
            palletization.action_validate_palletization()
        except UserError as error:
            return self.build_vas_outbound_palletization_result(False, str(error))
        return self.build_vas_outbound_palletization_result(True, _('Palletization validated.'), 'validated')

    @api.model
    def can_vas_outbound_palletization_direct(self, palletization, package):
        move_lines = self.get_vas_outbound_palletization_move_lines(palletization, package.id)
        if not move_lines or any(self.get_vas_outbound_palletization_remaining_quantity(palletization, line) != line.quantity for line in move_lines):
            return False, _('This source pallet already has palletization allocations.')
        stock_data = self.get_package_stock_set(package)
        if not stock_data['lines']:
            return False, _('No internal stock was found for this pallet.')
        if len(stock_data['location_ids']) != 1:
            return False, _('Pallet stock is split across multiple locations.')
        if self.has_untracked_serial_stock(stock_data['quants']):
            return False, _('This pallet contains serial-tracked stock without serial numbers.')
        stock_lines = stock_data['lines']
        demand_lines = self.get_package_demand_set(move_lines)
        if set(stock_lines) != set(demand_lines):
            return False, _('Pallet stock does not exactly match the outbound demand.')
        for key, stock_line in stock_lines.items():
            rounding = stock_line['product'].uom_id.rounding
            if float_compare(stock_line['quantity'], demand_lines[key]['quantity'], precision_rounding=rounding) != 0:
                return False, _('Pallet quantity does not exactly match the outbound demand.')
        return True, _('This is a whole pallet and may be directly outbound or palletized.')

    @api.model
    def process_vas_outbound_palletization_source_scan(self, code, palletization_id, destination_package_id=False):
        palletization = self.get_vas_outbound_palletization(palletization_id)
        self = self.with_context(vas_outbound_palletization_id=palletization.id, vas_outbound_palletization_barcode=code)
        if palletization.state not in ('pending', 'in_progress'):
            return self.build_vas_outbound_palletization_result(False, _('Reset palletization before scanning again.'), 'scan_source', {'destination_package_id': destination_package_id})
        destination_package = self.env['stock.quant.package'].browse(self.env['stock.quant.package'].sudo().search([('id', '=', destination_package_id)], limit=1).ids) if destination_package_id else self.env['stock.quant.package']
        if not destination_package:
            return self.build_vas_outbound_palletization_result(False, _('Scan a destination transport pallet first.'), 'scan_destination')
        package = self.get_outgoing_package_from_barcode(code)
        if package:
            package_move_lines = self.get_vas_outbound_palletization_move_lines(palletization, package.id)
            is_selected_destination = package.vas_outbound_palletization_id == palletization
            if is_selected_destination:
                return self.build_vas_outbound_palletization_result(True, _('Destination transport pallet %s selected.') % package.display_name, 'scan_source', {'destination_package_id': package.id})
            move_lines = self.get_vas_outbound_palletization_available_move_lines(palletization, package.id)
            if not move_lines:
                return self.build_vas_outbound_palletization_result(False, _('The scanned source pallet has no remaining picked quantity.'), 'scan_source', {'destination_package_id': destination_package.id})
            can_direct, message = self.can_vas_outbound_palletization_direct(palletization, package)
            if can_direct:
                return self.build_vas_outbound_palletization_result(True, message, 'choose_whole_handling', {'destination_package_id': destination_package.id, 'source_package_id': package.id, 'source_package_name': package.display_name})
            return self.build_vas_outbound_palletization_result(True, _('Source pallet %s is not a whole pallet. Scan a product to palletize loose goods. %s') % (package.display_name, message), 'scan_product', {'destination_package_id': destination_package.id, 'source_package_id': package.id, 'source_package_name': package.display_name})
        products = self.get_outgoing_product_from_barcode(code)
        loose_product_lines = self.get_vas_outbound_palletization_available_move_lines(palletization, False, products.id) if len(products) == 1 else self.env['stock.move.line']
        if len(products) == 1 and loose_product_lines:
            next_step = 'scan_serial' if products.tracking == 'serial' else 'scan_lot' if products.tracking == 'lot' else 'input_quantity'
            return self.build_vas_outbound_palletization_result(True, _('Loose product %s selected.') % products.display_name, next_step, {'destination_package_id': destination_package.id, 'product_id': products.id, 'product_name': products.display_name})
        return self.build_vas_outbound_palletization_result(False, _('Scan a source pallet, or scan a loose product that belongs to this outbound picking.'), 'scan_source', {'destination_package_id': destination_package.id})

    @api.model
    def process_vas_outbound_palletization_product_scan(self, code, palletization_id, source_package_id, destination_package_id=False):
        palletization = self.get_vas_outbound_palletization(palletization_id)
        self = self.with_context(vas_outbound_palletization_id=palletization.id, vas_outbound_palletization_barcode=code)
        products = self.get_outgoing_product_from_barcode(code)
        if len(products) != 1:
            return self.build_vas_outbound_palletization_result(False, _('Product barcode is not unique or was not found.'), 'scan_product', {'destination_package_id': destination_package_id, 'source_package_id': source_package_id})
        move_lines = self.get_vas_outbound_palletization_available_move_lines(palletization, source_package_id, products.id)
        if not move_lines:
            return self.build_vas_outbound_palletization_result(False, _('The product has no remaining picked quantity on this source.'), 'scan_product', {'destination_package_id': destination_package_id, 'source_package_id': source_package_id})
        next_step = 'scan_serial' if products.tracking == 'serial' else 'scan_lot' if products.tracking == 'lot' else 'input_quantity'
        return self.build_vas_outbound_palletization_result(True, _('Product %s selected.') % products.display_name, next_step, {'destination_package_id': destination_package_id, 'source_package_id': source_package_id, 'product_id': products.id, 'product_name': products.display_name})

    @api.model
    def create_vas_outbound_palletization_allocations(self, palletization, source_package_id, product_id, lot_id, quantity, destination_package_id):
        package_model = self.env['stock.quant.package']
        destination_package_ids = package_model.sudo().search([('id', '=', destination_package_id), ('vas_outbound_palletization_id', '=', palletization.id)], limit=1).ids
        destination_package = package_model.browse(destination_package_ids)
        if not destination_package:
            raise UserError(_('Select a transport pallet created for this palletization.'))
        if source_package_id and destination_package.id == source_package_id:
            raise UserError(_('Palletized goods must use a different destination pallet.'))
        move_lines = self.get_vas_outbound_palletization_available_move_lines(palletization, source_package_id, product_id, lot_id)
        remaining_quantity = self.parse_outgoing_quantity(quantity)
        values_list = []
        for move_line in move_lines:
            available_quantity = self.get_vas_outbound_palletization_remaining_quantity(palletization, move_line)
            allocated_quantity = min(available_quantity, remaining_quantity)
            if allocated_quantity > 0:
                values_list.append({'palletization_id': palletization.id, 'source_move_line_id': move_line.id, 'quantity': allocated_quantity, 'destination_package_id': destination_package.id, 'handling_type': 'palletize'})
                remaining_quantity -= allocated_quantity
            if remaining_quantity <= 0:
                break
        if remaining_quantity > 0:
            raise UserError(_('Quantity exceeds the remaining picked quantity.'))
        self.env['wd.vas.outbound.palletization.line'].create(values_list)
        return destination_package

    @api.model
    def get_vas_outbound_palletization_next_step_after_allocation(self, palletization, source_package_id, destination_package_id):
        if source_package_id and self.get_vas_outbound_palletization_available_move_lines(palletization, source_package_id):
            return 'scan_product', {'destination_package_id': destination_package_id, 'source_package_id': source_package_id}
        return 'scan_source', {'destination_package_id': destination_package_id}

    @api.model
    def process_vas_outbound_palletization_lot_scan(self, code, palletization_id, source_package_id, product_id, destination_package_id=False):
        palletization = self.get_vas_outbound_palletization(palletization_id)
        self = self.with_context(vas_outbound_palletization_id=palletization.id, vas_outbound_palletization_barcode=code)
        lot_model = self.env['stock.lot']
        product = self.env['product.product'].browse(product_id)
        next_step = 'scan_serial' if product.tracking == 'serial' else 'scan_lot'
        lot_ids = lot_model.sudo().search([('name', '=', code), ('product_id', '=', product_id)], limit=1).ids
        lot = lot_model.browse(lot_ids)
        if not lot or not self.get_vas_outbound_palletization_available_move_lines(palletization, source_package_id, product_id, lot.id):
            return self.build_vas_outbound_palletization_result(False, _('Lot or serial number was not found on the remaining picked goods.'), next_step, {'destination_package_id': destination_package_id, 'source_package_id': source_package_id, 'product_id': product_id})
        if lot.product_id.tracking == 'serial':
            try:
                destination_package = self.create_vas_outbound_palletization_allocations(palletization, source_package_id, product_id, lot.id, 1.0, destination_package_id)
            except UserError as error:
                return self.build_vas_outbound_palletization_result(False, str(error), next_step, {'destination_package_id': destination_package_id, 'source_package_id': source_package_id, 'product_id': product_id, 'lot_id': lot.id, 'lot_name': lot.name, 'tracking_number': lot.name})
            next_step, current = self.get_vas_outbound_palletization_next_step_after_allocation(palletization, source_package_id, destination_package.id)
            return self.build_vas_outbound_palletization_result(True, _('Serial number %s assigned to destination pallet %s.') % (lot.name, destination_package.display_name), next_step, current)
        return self.build_vas_outbound_palletization_result(True, _('Lot or serial number %s selected.') % lot.name, 'input_quantity', {'destination_package_id': destination_package_id, 'source_package_id': source_package_id, 'product_id': product_id, 'lot_id': lot.id, 'lot_name': lot.name})

    @api.model
    def process_vas_outbound_palletization_quantity(self, palletization_id, source_package_id, product_id, lot_id, quantity, destination_package_id=False):
        palletization = self.get_vas_outbound_palletization(palletization_id)
        self = self.with_context(vas_outbound_palletization_id=palletization.id, vas_outbound_palletization_barcode=str(quantity))
        scan_quantity = self.parse_outgoing_quantity(quantity)
        move_lines = self.get_vas_outbound_palletization_available_move_lines(palletization, source_package_id, product_id, lot_id)
        if not scan_quantity or not move_lines:
            return self.build_vas_outbound_palletization_result(False, _('Enter a valid remaining quantity.'), 'input_quantity', {'destination_package_id': destination_package_id, 'source_package_id': source_package_id, 'product_id': product_id, 'lot_id': lot_id})
        available_quantity = sum(self.get_vas_outbound_palletization_remaining_quantity(palletization, line) for line in move_lines)
        rounding = move_lines[:1].product_uom_id.rounding or move_lines[:1].product_id.uom_id.rounding
        if float_compare(scan_quantity, available_quantity, precision_rounding=rounding) > 0:
            return self.build_vas_outbound_palletization_result(False, _('Quantity exceeds the remaining picked quantity.'), 'input_quantity', {'destination_package_id': destination_package_id, 'source_package_id': source_package_id, 'product_id': product_id, 'lot_id': lot_id})
        if move_lines[:1].product_id.tracking == 'serial' and float_compare(scan_quantity, 1.0, precision_rounding=rounding) != 0:
            return self.build_vas_outbound_palletization_result(False, _('A serial number quantity must be exactly one.'), 'input_quantity', {'destination_package_id': destination_package_id, 'source_package_id': source_package_id, 'product_id': product_id, 'lot_id': lot_id})
        try:
            destination_package = self.create_vas_outbound_palletization_allocations(palletization, source_package_id, product_id, lot_id, scan_quantity, destination_package_id)
        except UserError as error:
            return self.build_vas_outbound_palletization_result(False, str(error), 'input_quantity', {'destination_package_id': destination_package_id, 'source_package_id': source_package_id, 'product_id': product_id, 'lot_id': lot_id})
        next_step, current = self.get_vas_outbound_palletization_next_step_after_allocation(palletization, source_package_id, destination_package.id)
        return self.build_vas_outbound_palletization_result(True, _('Palletization allocation recorded.'), next_step, current)

    @api.model
    def process_vas_outbound_palletization_destination_scan(self, code, palletization_id):
        palletization = self.get_vas_outbound_palletization(palletization_id)
        self = self.with_context(vas_outbound_palletization_id=palletization.id, vas_outbound_palletization_barcode=code)
        package = self.get_outgoing_package_from_barcode(code)
        if not package:
            return self.build_vas_outbound_palletization_result(False, _('Destination pallet was not found.'), 'scan_destination')
        if package.vas_outbound_palletization_id != palletization:
            return self.build_vas_outbound_palletization_result(False, _('Scan a transport pallet created for this palletization.'), 'scan_destination')
        return self.build_vas_outbound_palletization_result(True, _('Destination transport pallet %s selected.') % package.display_name, 'scan_source', {'destination_package_id': package.id})

    @api.model
    def action_vas_outbound_palletization_direct(self, palletization_id, source_package_id, destination_package_id=False):
        palletization = self.get_vas_outbound_palletization(palletization_id)
        self = self.with_context(vas_outbound_palletization_id=palletization.id)
        package_model = self.env['stock.quant.package']
        package_ids = package_model.sudo().search([('id', '=', source_package_id)], limit=1).ids
        package = package_model.browse(package_ids)
        can_direct, message = self.can_vas_outbound_palletization_direct(palletization, package)
        if not can_direct:
            return self.build_vas_outbound_palletization_result(False, message, 'scan_source', {'destination_package_id': destination_package_id})
        move_lines = self.get_vas_outbound_palletization_move_lines(palletization, package.id)
        self.env['wd.vas.outbound.palletization.line'].create([{'palletization_id': palletization.id, 'source_move_line_id': move_line.id, 'quantity': move_line.quantity, 'destination_package_id': package.id, 'handling_type': 'direct_outbound'} for move_line in move_lines])
        return self.build_vas_outbound_palletization_result(True, _('Whole pallet marked for direct outbound.'), 'scan_source', {'destination_package_id': destination_package_id})

    @api.model
    def action_vas_outbound_palletization_group_whole(self, palletization_id, source_package_id, destination_code=False, destination_package_id=False):
        palletization = self.get_vas_outbound_palletization(palletization_id)
        self = self.with_context(vas_outbound_palletization_id=palletization.id, vas_outbound_palletization_barcode=destination_code)
        source_package_model = self.env['stock.quant.package']
        source_package_ids = source_package_model.sudo().search([('id', '=', source_package_id)], limit=1).ids
        source_package = source_package_model.browse(source_package_ids)
        can_direct, message = self.can_vas_outbound_palletization_direct(palletization, source_package)
        if not can_direct:
            return self.build_vas_outbound_palletization_result(False, message, 'scan_source', {'destination_package_id': destination_package_id})
        destination_package = self.env['stock.quant.package'].browse(self.env['stock.quant.package'].sudo().search([('id', '=', destination_package_id)], limit=1).ids) if destination_package_id else self.get_outgoing_package_from_barcode(destination_code)
        if not destination_package or destination_package == source_package or destination_package.vas_outbound_palletization_id != palletization:
            return self.build_vas_outbound_palletization_result(False, _('Scan a different existing destination pallet.'), 'scan_destination', {'source_package_id': source_package_id})
        move_lines = self.get_vas_outbound_palletization_move_lines(palletization, source_package.id)
        self.env['wd.vas.outbound.palletization.line'].create([{'palletization_id': palletization.id, 'source_move_line_id': move_line.id, 'quantity': move_line.quantity, 'destination_package_id': destination_package.id, 'handling_type': 'palletize'} for move_line in move_lines])
        return self.build_vas_outbound_palletization_result(True, _('Whole pallet assigned to destination pallet %s.') % destination_package.display_name, 'scan_source', {'destination_package_id': destination_package.id})
