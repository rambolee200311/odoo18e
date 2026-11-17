from odoo import _, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    outbound_scan_mode = fields.Selection([('whole_pallet', 'Whole Pallet'), ('partial_pallet', 'Partial Pallet')], string='Outbound Scan Mode', copy=False, index=True)
    is_unspecified_pallet_outgoing = fields.Boolean(string='Unspecified Pallet Outgoing', copy=False, index=True)
    project_pallet_structure_mode = fields.Selection(related='project_id.pallet_structure_mode', string='Pallet Structure Mode', readonly=True)
    outbound_preparation_state = fields.Selection([('not_required', 'Not Required'), ('prepared', 'Prepared')], string='Outbound Preparation Status',tracking=True, required=True, default='not_required', readonly=True, copy=False, index=True)
    outbound_prepared_by_id = fields.Many2one('res.users', string='Outbound Prepared By', readonly=True, copy=False, tracking=True,ondelete='restrict')
    outbound_prepared_at = fields.Datetime(string='Outbound Prepared At', readonly=True,tracking=True, copy=False)

    def action_validate_secondary_outbound(self):
        for rec in self:
            if rec.picking_type_code != 'outgoing' or rec.state in ('done', 'cancel'):
                raise UserError(_('Only pending outgoing pickings can be confirmed for secondary outbound.'))
        self.with_context(skip_secondary_outbound_validation=True, skip_backorder=True).button_validate()
        if any(rec.state != 'done' for rec in self):
            raise UserError(_('Secondary outbound confirmation could not complete all outgoing pickings.'))
        return True

    def button_validate(self):
        secondary_outbound_pickings = self.filtered(lambda rec: not self.env.context.get('skip_secondary_outbound_validation') and rec.picking_type_code == 'outgoing' and rec.project_id.outbound_palletization_enabled and rec.state not in ('done', 'cancel'))
        if secondary_outbound_pickings:
            if secondary_outbound_pickings != self:
                raise UserError(_('Pickings with different outbound completion workflows must be validated separately.'))
            preparation_pickings = secondary_outbound_pickings.filtered(lambda rec: rec.outbound_preparation_state != 'prepared')
            if preparation_pickings:
                for rec in preparation_pickings:
                    rec.write({'outbound_preparation_state': 'prepared', 'outbound_prepared_by_id': self.env.user.id, 'outbound_prepared_at': fields.Datetime.now()})
                return True
            for rec in secondary_outbound_pickings:
                unconfirmed_move_lines = rec.move_line_ids.filtered(lambda line: line.state != 'cancel' and line.quantity > 0 and not line.secondary_outbound_confirmed)
                if unconfirmed_move_lines:
                    raise UserError(_('Complete secondary outbound confirmation before validating outgoing picking %s.') % rec.name)
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
