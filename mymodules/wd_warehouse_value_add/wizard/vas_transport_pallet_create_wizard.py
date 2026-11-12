# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class VasTransportPalletCreateWizard(models.TransientModel):
    _name = 'wd.vas.transport.pallet.create.wizard'
    _description = 'Create VAS Transport Pallets'

    palletization_id = fields.Many2one('wd.vas.outbound.palletization', string='Palletization', required=True, readonly=True, ondelete='cascade')
    pallet_count = fields.Integer(string='Transport Pallet Quantity', required=True, default=1)

    def action_create(self):
        for rec in self:
            packages = rec.palletization_id.action_create_transport_pallets(rec.pallet_count)
            if not packages:
                raise UserError(_('No transport pallets were created.'))
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': _('Created'), 'message': _('Transport pallets were created.'), 'type': 'success', 'next': {'type': 'ir.actions.client', 'tag': 'reload'}}}

    def action_create_and_print(self):
        for rec in self:
            packages = rec.palletization_id.action_create_transport_pallets(rec.pallet_count)
            if not packages:
                raise UserError(_('No transport pallets were created.'))
            return self.env.ref('wd_warehouse_value_add.action_report_vas_transport_pallet_label').report_action(packages)
        return False
