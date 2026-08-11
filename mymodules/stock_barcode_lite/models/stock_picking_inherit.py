# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare
from odoo import api, fields, models

class StockPicking(models.Model):
    _inherit = "stock.picking"

    outbound_scan_mode = fields.Selection([("whole_pallet", "Whole Pallet"), ("partial_pallet", "Partial Pallet")],
                                          string="Outbound Scan Mode", copy=False, index=True)
    new_pallet_count = fields.Integer(string="New Pallet Count", default=0, copy=False)
    project_name = fields.Char(string='Project Name', related='project_id.name',stored=True)
    barcode_scan_mode = fields.Selection(related='project_id.barcode_scan_mode', store=True)

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
            if (
                    inbound_order
                    and inbound_order.project.name == "SUNRISE"
                    and rec.state != "done"
                    and not rec.return_id
                    and rec.picking_type_id.code == "incoming"
                    and inbound_order.stock_picking_id == rec
            ):
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
        for rec in self:
            if not skip_scan_validation:
                rec.check_incoming_pallet_location_updated()
                rec.check_outgoing_pallet_scan_completed()
            if (
                rec.project_name == "SUNRISE"
                and rec.picking_type_id.code == "outgoing"
                and rec.outbound_order_id
                and rec.state not in ("done", "cancel")
                and rec.new_pallet_count < 0
            ):
                raise UserError(_("New pallet count must be greater than or equal to zero."))
        result = super().button_validate()
        quant_model = self.env["stock.quant"].sudo()
        for rec in self:
            if rec.picking_type_id.code not in ("incoming", "outgoing") or rec.state != "done":
                continue
            package_records = rec.move_line_ids.mapped("package_id") | rec.move_line_ids.mapped("result_package_id")
            for package in package_records:
                if package.lifecycle_state == "closed":
                    continue
                package_quant = quant_model.search([
                    ("package_id", "=", package.id),
                    ("location_id.usage", "=", "internal"),
                    ("quantity", ">", 0),
                ], limit=1)
                values = {}
                if package_quant:
                    if package.lifecycle_state != "active":
                        values["lifecycle_state"] = "active"
                    if rec.picking_type_id.code == "incoming" and not package.lifecycle_start_datetime:
                        values["lifecycle_start_datetime"] = rec.date_done or fields.Datetime.now()
                elif package.lifecycle_state == "active":
                    values.update({
                        "lifecycle_state": "consumed",
                        "consumed_datetime": rec.date_done or fields.Datetime.now(),
                    })
                if values:
                    package.write(values)
        return result

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
