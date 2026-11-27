# -*- coding: utf-8 -*-

from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):
        result = super().button_validate()
        outbound_order_ids = []
        carton_weight_order_ids = []
        for rec in self:
            if rec.state == "done" and rec.picking_type_id.code == "outgoing" and rec.outbound_order_id:
                outbound_order_ids.append(rec.outbound_order_id.id)
                if not rec.project_id.outbound_palletization_enabled:
                    carton_weight_order_ids.append(rec.outbound_order_id.id)
            elif rec.picking_type_id.code == "outgoing" and rec.outbound_order_id and rec.project_id.outbound_palletization_enabled and rec.outbound_preparation_state == "prepared":
                carton_weight_order_ids.append(rec.outbound_order_id.id)
        if carton_weight_order_ids:
            self.env["world.depot.outbound.order"].browse(carton_weight_order_ids).apply_outbound_carton_weight_charges()
        if outbound_order_ids:
            self.env["world.depot.outbound.order"].browse(outbound_order_ids).apply_outbound_picking_charges()
        return result
