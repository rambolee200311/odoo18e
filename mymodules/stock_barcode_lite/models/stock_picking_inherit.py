# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare
from odoo import api, fields, models

class StockPicking(models.Model):
    _inherit = "stock.picking"
    _order = "id desc"

    outbound_scan_mode = fields.Selection([("whole_pallet", "Whole Pallet"), ("partial_pallet", "Partial Pallet")],
                                          string="Outbound Scan Mode", copy=False, index=True)
    is_unspecified_pallet_outgoing = fields.Boolean(string="Unspecified Pallet Outgoing", copy=False, index=True)
    new_pallet_count = fields.Integer(string="New Pallet Count", default=0, copy=False)
    project_name = fields.Char(string='Project Name', related='project_id.name',stored=True)
    barcode_scan_mode = fields.Selection(related='project_id.barcode_scan_mode', store=True)

    def check_native_barcode_scan_allowed(self):
        for rec in self:
            if rec.project_id.barcode_scan_mode == "custom" and rec.project_id.name != "HOYMILES":
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
                rec.check_unspecified_pallet_outgoing_scan_completed()
                rec.check_custom_barcode_serial_tracking()
            if (
                rec.project_name == "SUNRISE"
                and rec.picking_type_id.code == "outgoing"
                and rec.outbound_order_id
                and rec.state not in ("done", "cancel")
                and rec.new_pallet_count < 0
            ):
                raise UserError(_("New pallet count must be greater than or equal to zero."))
        result = super().button_validate()
        self.update_sunrise_inbound_pallet_locations()
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

    def update_sunrise_inbound_pallet_locations(self):
        move_line_model = self.env["stock.move.line"].sudo()
        pallet_model = self.env["world.depot.inbound.order.product"]

        for rec in self:
            inbound_order = rec.inbound_order_id
            if rec.project_name != "SUNRISE" or rec.picking_type_id.code != "incoming" or rec.state != "done" or not inbound_order:
                continue
            pallet_lines = pallet_model.browse(inbound_order.inbound_order_product_ids.ids)
            if not pallet_lines:
                continue
            move_lines = move_line_model.search([
                ("picking_id.inbound_order_id", "=", inbound_order.id),
                ("picking_id.picking_type_id.code", "=", "incoming"),
                ("inbound_order_product_pallet_id", "!=", False),
                ("state", "=", "done"),
                ("quantity", ">", 0),
            ])
            location_name_map = {}
            for move_line in move_lines:
                pallet_id = move_line.inbound_order_product_pallet_id.inbound_order_product_id.id
                location_name = move_line.location_dest_id.complete_name or move_line.location_dest_id.display_name
                if pallet_id and location_name:
                    location_name_map.setdefault(pallet_id, set()).add(location_name)
            for pallet_line in pallet_lines:
                inbound_location = ", ".join(sorted(location_name_map.get(pallet_line.id, set())))
                if inbound_location and pallet_line.inbound_location != inbound_location:
                    pallet_line.write({"inbound_location": inbound_location})

    def check_incoming_pallet_location_updated(self):
        for rec in self:
            if rec.barcode_scan_mode != "custom":
                continue
            if rec.project_id.name == "HOYMILES" and self.env.context.get("barcode_trigger"):
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

    def check_unspecified_pallet_outgoing_scan_completed(self):
        move_model = self.env["stock.move"]
        move_line_model = self.env["stock.move.line"]
        for rec in self:
            if not rec.is_unspecified_pallet_outgoing or rec.state in ("done", "cancel"):
                continue
            moves = move_model.sudo().search([("picking_id", "=", rec.id), ("state", "!=", "cancel")], order="id")
            scanned_lines = move_line_model.sudo().search([("move_id", "in", moves.ids), ("state", "!=", "cancel"), ("is_outbound_scanned", "=", True)]) if moves else move_line_model
            scanned_qty_by_move = {}
            for line in scanned_lines:
                scanned_qty_by_move[line.move_id.id] = scanned_qty_by_move.get(line.move_id.id, 0.0) + (line.outbound_scanned_quantity or 0.0)
            missing_messages = []
            for move in moves:
                scanned_qty = scanned_qty_by_move.get(move.id, 0.0)
                if float_compare(scanned_qty, move.product_uom_qty or 0.0, precision_rounding=move.product_uom.rounding) != 0:
                    missing_messages.append("%s (%s/%s)" % (move.product_id.display_name, scanned_qty, move.product_uom_qty))
            if missing_messages:
                raise UserError(_("Please complete actual pallet scanning before validating. Missing products: %s") % "; ".join(missing_messages))

    def check_custom_barcode_serial_tracking(self):
        for rec in self:
            if rec.barcode_scan_mode != "custom" or rec.picking_type_id.code not in ("incoming", "outgoing") or rec.state in ("done", "cancel"):
                continue
            serial_lines = rec.move_line_ids.filtered(
                lambda line: line.product_id.tracking == "serial" and line.quantity > 0 and line.state != "cancel"
            )
            if not serial_lines:
                continue
            invalid_lines = []
            serial_keys = set()
            for line in serial_lines:
                rounding = line.product_uom_id.rounding or line.product_id.uom_id.rounding
                serial_name = line.lot_id.name or line.lot_name
                if float_compare(line.quantity, 1.0, precision_rounding=rounding) != 0:
                    invalid_lines.append(_("%s has quantity %s") % (line.product_id.display_name, line.quantity))
                    continue
                if rec.picking_type_id.code == "incoming":
                    if not serial_name:
                        invalid_lines.append(_("%s has no serial number") % line.product_id.display_name)
                        continue
                    if line.lot_name and not rec.picking_type_id.use_create_lots:
                        invalid_lines.append(_("%s cannot create serial number %s") % (line.product_id.display_name, line.lot_name))
                        continue
                elif not line.lot_id:
                    invalid_lines.append(_("%s has no serial number") % line.product_id.display_name)
                    continue
                elif not line.is_outbound_scanned or float_compare(line.outbound_scanned_quantity, line.quantity, precision_rounding=rounding) != 0:
                    invalid_lines.append(_("%s serial number %s has not been scanned") % (line.product_id.display_name, serial_name))
                    continue
                serial_key = (line.product_id.id, serial_name)
                if serial_key in serial_keys:
                    invalid_lines.append(_("%s serial number %s is duplicated") % (line.product_id.display_name, serial_name))
                    continue
                serial_keys.add(serial_key)
            if invalid_lines:
                raise UserError(
                    _("Please complete serial number scanning before validating: %s") % "; ".join(invalid_lines)
                )


class StockLotInherit(models.Model):
    _inherit = "stock.lot"

    gross_weight = fields.Float(string="Gross Weight (kg)", copy=False)
    product_dimensions = fields.Char(string="Product Dimensions (m)", copy=False)
