# -*- coding: utf-8 -*-

from odoo import models


class VasOutboundPalletization(models.Model):
    _inherit = 'wd.vas.outbound.palletization'

    def get_validation_error(self):
        validation_error = super().get_validation_error()
        if validation_error:
            return validation_error
        for rec in self:
            if rec.vas_order_id.source_model != 'world.depot.outbound.order':
                continue
            unprepared_pickings = rec.picking_ids.filtered(lambda picking: picking.outbound_preparation_state != 'prepared')
            if unprepared_pickings:
                return 'Complete outbound picking before validating palletization: %s.' % ', '.join(unprepared_pickings.mapped('name'))
        return False
