# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class InboundActualPalletCreateWizard(models.TransientModel):
    _name = "inbound.actual.pallet.create.wizard"
    _description = "Create Actual Inbound Pallets"

    inbound_order_id = fields.Many2one("world.depot.inbound.order", string="Inbound Order", required=True, readonly=True, copy=False, index=True)
    pallet_count = fields.Integer(string="Pallet Count", required=True, default=1)

    def action_create_actual_pallets(self):
        for rec in self:
            if rec.pallet_count <= 0:
                raise UserError(_("Pallet count must be greater than zero."))
            rec.inbound_order_id.action_create_actual_pallets(rec.pallet_count)
        return {"type": "ir.actions.client", "tag": "reload"}
