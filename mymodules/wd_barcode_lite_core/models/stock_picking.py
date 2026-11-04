from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    outbound_scan_mode = fields.Selection([('whole_pallet', 'Whole Pallet'), ('partial_pallet', 'Partial Pallet')], string='Outbound Scan Mode', copy=False, index=True)
    is_unspecified_pallet_outgoing = fields.Boolean(string='Unspecified Pallet Outgoing', copy=False, index=True)

    def button_validate(self):
        result = super().button_validate()
        quant_model = self.env['stock.quant'].sudo()
        for rec in self:
            if rec.picking_type_id.code not in ('incoming', 'outgoing') or rec.state != 'done':
                continue
            package_records = rec.move_line_ids.mapped('package_id') | rec.move_line_ids.mapped('result_package_id')
            for package in package_records:
                if package.lifecycle_state == 'closed':
                    continue
                package_quant = quant_model.search([('package_id', '=', package.id), ('location_id.usage', '=', 'internal'), ('quantity', '>', 0)], limit=1)
                values = {}
                if package_quant:
                    if package.lifecycle_state != 'active':
                        values['lifecycle_state'] = 'active'
                    if rec.picking_type_id.code == 'incoming' and not package.lifecycle_start_datetime:
                        values['lifecycle_start_datetime'] = rec.date_done or fields.Datetime.now()
                elif package.lifecycle_state == 'active':
                    values.update({'lifecycle_state': 'consumed', 'consumed_datetime': rec.date_done or fields.Datetime.now()})
                if values:
                    package.write(values)
        return result
