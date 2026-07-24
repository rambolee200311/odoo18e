# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare
from odoo import api, fields, models

class StockPicking(models.Model):
    _inherit = "stock.picking"

    outbound_scan_mode = fields.Selection([("whole_pallet", "Whole Pallet"), ("partial_pallet", "Partial Pallet")],
                                          string="Outbound Scan Mode", copy=False, index=True)
    project_name = fields.Char(string='Project Name', related='project_id.name',stored=True)

    def check_native_barcode_scan_allowed(self):
        for rec in self:
            if rec.project_id.barcode_scan_mode == "custom":
                raise UserError(_("This picking must use Custom Barcode Lite scanning."))

    def action_open_picking_client_action(self):
        self.check_native_barcode_scan_allowed()
        return super().action_open_picking_client_action()

    def _get_stock_barcode_data(self):
        self.check_native_barcode_scan_allowed()
        return super()._get_stock_barcode_data()

    def unlink(self):
        inbound_orders = self.env["world.depot.inbound.order"]

        for rec in self:
            inbound_order = rec.inbound_order_id
            if inbound_order and inbound_order.project.name == "SUNRISE" and rec.state != "done":
                inbound_orders |= inbound_order

        res = super().unlink()

        for inbound_order in inbound_orders:
            inbound_order.action_delete_sunrise_packages_before_cancel()
            inbound_order.write({"stock_picking_id": False})

        return res
    def chenyang_force_button_validate(self):
        return self.with_context(
            skip_chenyang_scan_validation=True,
        ).button_validate()


    def button_validate(self):
        skip_scan_validation = self.env.context.get("skip_chenyang_scan_validation")
        if not skip_scan_validation:
            for rec in self:
                rec.check_incoming_pallet_location_updated()
                rec.check_outgoing_pallet_scan_completed()
        return super().button_validate()

    def check_incoming_pallet_location_updated(self):
        for rec in self:
            if rec.project_name != "SUNRISE":
                continue
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

    def check_outgoing_pallet_scan_completed(self):
        for rec in self:
            if rec.project_name != "SUNRISE":
                continue
            if rec.picking_type_id.code != "outgoing" or not rec.outbound_order_id or rec.state in ("done", "cancel"):
                continue
            package_lines = rec.move_line_ids.filtered(
                lambda line: line.package_id and line.quantity > 0 and line.state != "cancel"
            )
            missing_messages = []
            for line in package_lines:
                rounding = line.product_uom_id.rounding or line.product_id.uom_id.rounding
                if (
                    not line.is_outbound_scanned
                    or float_compare(line.outbound_scanned_quantity, line.quantity, precision_rounding=rounding) != 0
                ):
                    missing_messages.append(
                        "%s / %s / %s (%s/%s)"
                        % (
                            line.package_id.name or line.package_id.barcode or line.package_id.display_name,
                            line.product_id.display_name,
                            line.lot_id.name or "-",
                            line.outbound_scanned_quantity or 0.0,
                            line.quantity or 0.0,
                        )
                    )
            if missing_messages:
                raise UserError(
                    _("Please complete outbound scanning before validating. Missing lines: %s")
                    % "; ".join(missing_messages)
                )
