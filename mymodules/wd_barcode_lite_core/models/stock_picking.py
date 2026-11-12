from odoo import _, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    outbound_scan_mode = fields.Selection([('whole_pallet', 'Whole Pallet'), ('partial_pallet', 'Partial Pallet')], string='Outbound Scan Mode', copy=False, index=True)
    is_unspecified_pallet_outgoing = fields.Boolean(string='Unspecified Pallet Outgoing', copy=False, index=True)
    project_pallet_structure_mode = fields.Selection(related='project_id.pallet_structure_mode', string='Pallet Structure Mode', readonly=True)
    outbound_preparation_state = fields.Selection([('not_required', 'Not Required'), ('prepared', 'Prepared')], string='Outbound Preparation Status', required=True, default='not_required', readonly=True, copy=False, index=True)
    outbound_prepared_by_id = fields.Many2one('res.users', string='Outbound Prepared By', readonly=True, copy=False, ondelete='restrict')
    outbound_prepared_at = fields.Datetime(string='Outbound Prepared At', readonly=True, copy=False)

    def button_validate(self):
        preparation_pickings = self.filtered(lambda rec: not self.env.context.get('skip_outbound_palletization_preparation') and rec.picking_type_code == 'outgoing' and rec.project_id.outbound_palletization_enabled and rec.state not in ('done', 'cancel'))
        if preparation_pickings:
            if preparation_pickings != self:
                raise UserError(_('Pickings with different outbound completion workflows must be validated separately.'))
            for rec in preparation_pickings:
                rec.write({'outbound_preparation_state': 'prepared', 'outbound_prepared_by_id': self.env.user.id, 'outbound_prepared_at': fields.Datetime.now()})
            return True
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
