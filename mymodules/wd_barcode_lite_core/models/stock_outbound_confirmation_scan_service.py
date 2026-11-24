from odoo import _, api, models
from odoo.exceptions import UserError


class StockOutboundConfirmationScanService(models.AbstractModel):
    _inherit = 'stock.barcode.lite.scan.service'

    @api.model
    def get_outbound_confirmation_pickings_from_barcode(self, code):
        picking_model = self.env['stock.picking']
        picking_ids = picking_model.sudo().search([('name', '=', code), ('picking_type_code', '=', 'outgoing'), ('state', 'not in', ('done', 'cancel'))]).ids
        return picking_model.browse(picking_ids)

    @api.model
    def process_outbound_confirmation_scan(self, code, confirmation_id=False):
        code = (code or '').strip()
        if not code:
            raise UserError(_('Please scan a barcode.'))
        confirmation_model = self.env['stock.outbound.confirmation']
        if not confirmation_id:
            pickings = self.get_outbound_confirmation_pickings_from_barcode(code)
            confirmation = confirmation_model.get_or_create_for_pickings(pickings.ids)
            next_step = 'scan_destination_pallet' if confirmation.confirmation_lines else 'confirm_unpacked' if confirmation.unpackaged_move_line_ids else 'complete'
            return self.build_outbound_confirmation_result(confirmation, _('Outbound confirmation selected.'), next_step)
        confirmation_ids = confirmation_model.sudo().search([('id', '=', confirmation_id), ('state', '=', 'scanning')], limit=1).ids
        confirmation = confirmation_model.browse(confirmation_ids)
        if not confirmation:
            raise UserError(_('The outbound confirmation is no longer available.'))
        confirmation.check_access_rights('read')
        confirmation.check_access_rule('read')
        package = self.get_package_from_barcode(code)
        if not package:
            raise UserError(_('Destination pallet was not found.'))
        confirmation.action_scan_destination_package(package.id)
        next_step = 'scan_destination_pallet' if confirmation.confirmation_lines else 'confirm_unpacked' if confirmation.unpackaged_move_line_ids else 'complete'
        return self.build_outbound_confirmation_result(confirmation, _('Destination pallet scanned.'), next_step)

    @api.model
    def action_confirm_outbound_confirmation(self, confirmation_id, include_unpacked_lines=False):
        confirmation_model = self.env['stock.outbound.confirmation']
        confirmation_ids = confirmation_model.sudo().search([('id', '=', confirmation_id), ('state', '=', 'scanning')], limit=1).ids
        confirmation = confirmation_model.browse(confirmation_ids)
        if not confirmation:
            raise UserError(_('The outbound confirmation is no longer available.'))
        confirmation.check_access_rights('write')
        confirmation.check_access_rule('write')
        result = confirmation.action_confirm_secondary_outbound(include_unpacked_lines=include_unpacked_lines)
        result_list = result if isinstance(result, list) else [result]
        for confirmation_result in result_list:
            next_confirmation_id = confirmation_result.get('next_confirmation_id')
            next_confirmation = confirmation_model.browse(next_confirmation_id) if next_confirmation_id else confirmation_model
            confirmation_result.update({'success': True, 'type': 'outbound_confirmation', 'current': {'outbound_order_id': confirmation.outbound_order_id.id if 'outbound_order_id' in confirmation._fields else False, 'confirmation_id': confirmation_result.get('confirmation_id')}, 'next_step': 'scan_destination_pallet' if next_confirmation.confirmation_lines else 'confirm_unpacked' if next_confirmation.unpackaged_move_line_ids else 'complete'})
        return result

    @api.model
    def build_outbound_confirmation_result(self, confirmation, message, next_step):
        return {'success': True, 'type': 'outbound_confirmation', 'message': message, 'current': {'outbound_order_id': confirmation.outbound_order_id.id if 'outbound_order_id' in confirmation._fields else False, 'confirmation_id': confirmation.id}, 'next_step': next_step, 'confirmation': {'id': confirmation.id, 'state': confirmation.state, 'mode': confirmation.confirmation_mode}, 'destination_pallets': [{'id': line.destination_package_id.id, 'name': line.destination_package_id.display_name, 'barcode': line.destination_package_id.barcode or line.destination_package_id.name, 'is_scanned': line.state == 'scanned'} for line in confirmation.confirmation_lines], 'summary': {'total_destination_pallets': len(confirmation.confirmation_lines), 'scanned_destination_pallets': len(confirmation.confirmation_lines.filtered(lambda line: line.state == 'scanned')), 'unpackaged_move_lines': len(confirmation.available_unpackaged_move_line_ids)}}
