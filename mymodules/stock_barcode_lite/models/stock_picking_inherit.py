# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def action_open_incoming_scan_wizard(self):
        for rec in self:
            if rec.picking_type_id.code != "incoming":
                raise UserError(_("Only incoming pickings can use incoming scan."))
            if rec.state in ("done", "cancel"):
                raise UserError(_("Done or cancelled pickings cannot use incoming scan."))
            wizard = self.env["stock.barcode.lite.incoming.scan.wizard"].create({
                "picking_id": rec.id,
                "message": _("Incoming picking %s selected.") % rec.name,
            })
            return {
                "type": "ir.actions.act_window",
                "name": _("Incoming Scan"),
                "res_model": "stock.barcode.lite.incoming.scan.wizard",
                "view_mode": "form",
                "res_id": wizard.id,
                "target": "new",
            }
        return False

    def button_validate(self):
        for rec in self:
            rec.check_incoming_pallet_location_updated()
        return super().button_validate()

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
