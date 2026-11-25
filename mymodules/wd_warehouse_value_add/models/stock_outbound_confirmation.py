from odoo import _, api, models
from odoo.exceptions import UserError


class StockOutboundConfirmation(models.Model):
    _inherit = 'stock.outbound.confirmation'

    @api.model
    def get_or_create_for_pickings(self, picking_ids):
        palletization_model = self.env['wd.vas.outbound.palletization']
        palletization_ids = palletization_model.sudo().search([('picking_ids', 'in', picking_ids), ('state', '=', 'in_progress')]).ids
        palletizations = palletization_model.browse(palletization_ids)
        if palletizations:
            raise UserError(_('Outbound palletization %s is not validated. Validate it first, or cancel it before secondary outbound confirmation.') % ', '.join(palletizations.mapped('name')))
        return super().get_or_create_for_pickings(picking_ids)

    def action_confirm_secondary_outbound(self, include_unpacked_lines=False):
        palletization_model = self.env['wd.vas.outbound.palletization']
        for rec in self:
            palletization_ids = palletization_model.sudo().search([('picking_ids', 'in', rec.picking_line_ids.ids), ('state', '=', 'in_progress')]).ids
            palletizations = palletization_model.browse(palletization_ids)
            if palletizations:
                raise UserError(_('Outbound palletization %s is not validated. Validate it first, or cancel it before secondary outbound confirmation.') % ', '.join(palletizations.mapped('name')))
        return super().action_confirm_secondary_outbound(include_unpacked_lines=include_unpacked_lines)
