from odoo import api, fields, models


class StockOutboundConfirmation(models.Model):
    _inherit = 'stock.outbound.confirmation'

    outbound_order_id = fields.Many2one('world.depot.outbound.order', string='Outbound Order', readonly=True, copy=False, index=True, ondelete='restrict')

    def action_confirm_secondary_outbound(self, include_unpacked_lines=False):
        result = super().action_confirm_secondary_outbound(include_unpacked_lines=include_unpacked_lines)
        confirmation_results = result if isinstance(result, list) else [result]
        final_confirmation_ids = [confirmation_result.get('confirmation_id') for confirmation_result in confirmation_results if confirmation_result.get('is_final_batch')]
        for rec in self.filtered(lambda confirmation: confirmation.id in final_confirmation_ids):
            outbound_order = rec.outbound_order_id
            outbound_pickings = outbound_order.outgoing_picking_lines.filtered(lambda picking: picking.state != 'cancel')
            if outbound_pickings and all(picking.state == 'done' for picking in outbound_pickings):
                completed_datetimes = outbound_pickings.mapped('date_done')
                if completed_datetimes:
                    outbound_order.write({'actual_outbound_datetime': max(completed_datetimes)})
        return result


class WorldDepotOutboundOrder(models.Model):
    _inherit = 'world.depot.outbound.order'

    secondary_outbound_confirmation_lines = fields.One2many('stock.outbound.confirmation', 'outbound_order_id', string='Secondary Outbound Confirmations', copy=False)


class StockBarcodeLiteScanService(models.AbstractModel):
    _inherit = 'stock.barcode.lite.scan.service'

    @api.model
    def get_outbound_confirmation_pickings_from_barcode(self, code):
        outbound_order_model = self.env['world.depot.outbound.order']
        outbound_order_ids = outbound_order_model.sudo().search([('billno', '=', (code or '').strip())], limit=1).ids
        if not outbound_order_ids:
            return self.env['stock.picking'].browse()
        picking_model = self.env['stock.picking']
        picking_ids = picking_model.sudo().search([('outbound_order_id', 'in', outbound_order_ids), ('picking_type_code', '=', 'outgoing'), ('state', 'not in', ('done', 'cancel'))]).ids
        return picking_model.browse(picking_ids)

    @api.model
    def process_outbound_confirmation_scan(self, code, confirmation_id=False):
        result = super().process_outbound_confirmation_scan(code, confirmation_id=confirmation_id)
        if confirmation_id or not result.get('success'):
            return result
        outbound_order_model = self.env['world.depot.outbound.order']
        outbound_order_ids = outbound_order_model.sudo().search([('billno', '=', (code or '').strip())], limit=1).ids
        confirmation_id = result.get('confirmation', {}).get('id')
        if not outbound_order_ids or not confirmation_id:
            return result
        outbound_order = outbound_order_model.browse(outbound_order_ids)
        confirmation = self.env['stock.outbound.confirmation'].browse(confirmation_id)
        if confirmation and not confirmation.outbound_order_id:
            confirmation.write({'outbound_order_id': outbound_order.id})
        if confirmation_id and result.get('current'):
            result['current']['outbound_order_id'] = outbound_order.id
        return result
