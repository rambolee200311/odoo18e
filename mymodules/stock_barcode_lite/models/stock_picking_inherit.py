# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"


    # def button_validate(self):
    #     for rec in self:
    #         rec.check_incoming_pallet_location_updated()
    #     return super().button_validate()

    def check_incoming_pallet_location_updated(self):
        for rec in self:
            if rec.picking_type_id.code != "incoming" or not rec.inbound_order_id or rec.state in ("done", "cancel"):
                continue
            package_lines = rec.move_line_ids.filtered(lambda line: line.result_package_id)
            missing_lines = package_lines.filtered(lambda line: not line.is_location_updated or not line.location_dest_id)
            if missing_lines:
                package_names = sorted(set(missing_lines.mapped("result_package_id.name")))
                raise UserError(
                    _("Please scan locations for all inbound pallets before validating. Missing pallets: %s")
                    % ", ".join(package_names)
                )
