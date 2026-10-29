# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class StockBarcodeLiteScanService(models.AbstractModel):
    _name = "stock.barcode.lite.scan.service"
    _description = "Stock Barcode Lite Scan Service"

    @api.model
    def process_incoming_scan_barcode(self, code, picking_id=False, current_location_id=False, current_package_id=False, current_product_id=False):

        code = (code or "").strip()
        if not code:
            return self.build_scan_result(
                "error",
                _("Error"),
                _("Please scan a barcode."),
                barcode=code,
                picking_id=picking_id,
                location_id=current_location_id,
                package_id=current_package_id,
                product_id=current_product_id,
                action_name="scan_error",
                success=False,
            )
        if current_package_id:
            return self.process_incoming_serial_context_scan(
                code,
                picking_id=picking_id,
                current_location_id=current_location_id,
                current_package_id=current_package_id,
                current_product_id=current_product_id,
            )
        if not picking_id:
            picking = self.get_picking_from_barcode(code)
            if not picking:
                return self.build_scan_result(
                    "error",
                    _("Error"),
                    _("Please scan incoming picking first."),
                    barcode=code,
                    picking_id=False,
                    location_id=False,
                    action_name="missing_picking",
                    success=False,
                )

            if picking.state == "done":
                return self.build_scan_result(
                    "picking",
                    _("Incoming Picking"),
                    _("Incoming picking %s is completed. Read-only view.") % picking.name,
                    barcode=code,
                    picking_id=picking.id,
                    location_id=False,
                    action_name="view_completed_picking",
                    success=True,
                    next_step="completed",
                )
            return self.build_scan_result(
                "picking",
                _("Incoming Picking"),
                _("Incoming picking %s selected.") % picking.name,
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                action_name="select_picking",
                success=True,
            )
        if not current_location_id:
            location = self.get_location_from_barcode(code)
            if location:
                return self.build_scan_result(
                    "location", _("Location"),
                    _("Current location changed to %s.") % location.display_name,
                    barcode=code,
                    picking_id=picking_id,
                    location_id=location.id,
                    action_name="select_location",
                    success=True,
                )

            return self.build_scan_result(
                "error", _("Error"), _("Please scan location first."),
                barcode=code,
                picking_id=picking_id,
                location_id=False,
                action_name="missing_location",
                success=False,
            )

        location = self.get_location_from_barcode(code)
        if location:
            return self.build_scan_result(
                "location", _("Location"),
                _("Current location changed to %s.") % location.display_name,
                barcode=code,
                picking_id=picking_id,
                location_id=location.id,
                action_name="select_location",
                success=True,
            )

        package = self.get_package_from_barcode(code)
        if package:
            return self.process_incoming_package_scan(code, package, picking_id, current_location_id)

        return self.build_scan_result(
            "unknown", _("Unknown"), _("Barcode not recognized: %s") % code,
            barcode=code,
            picking_id=picking_id,
            location_id=current_location_id,
            action_name="barcode_not_found",
            success=False,
        )

    @api.model
    def process_incoming_package_scan(self, code, package, picking_id=False, current_location_id=False):
        if not picking_id:
            return self.build_scan_result(
                "package",
                _("Pallet"),
                _("Please scan incoming picking first."),
                barcode=code,
                package_id=package.id,
                action_name="missing_picking",
                success=False,
            )
        picking = self.env["stock.picking"].sudo().search([
            ("id", "=", picking_id),
            ("picking_type_id.code", "=", "incoming"),
            ("state", "not in", ("done", "cancel")),
        ], limit=1)
        if not picking:
            return self.build_scan_result(
                "package",
                _("Pallet"),
                _("Done, cancelled, or invalid incoming picking cannot be updated."),
                barcode=code,
                picking_id=picking_id,
                package_id=package.id,
                action_name="invalid_picking",
                success=False,
            )
        if not current_location_id:
            return self.build_scan_result(
                "package",
                _("Pallet"),
                _("Please scan location first."),
                barcode=code,
                picking_id=picking.id,
                package_id=package.id,
                action_name="missing_location",
                success=False,
            )
        location = self.env["stock.location"].sudo().search([
            ("id", "=", current_location_id),
            ("usage", "=", "internal"),
        ], limit=1)
        if not location:
            return self.build_scan_result(
                "package",
                _("Pallet"),
                _("Please scan a valid internal location first."),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                action_name="invalid_location",
                success=False,
            )

        move_lines = self.get_package_move_lines(picking, package)
        if not move_lines:
            return self.build_scan_result(
                "package",
                _("Pallet"),
                _("No move lines found for pallet %s in current picking.") % package.name,
                barcode=code,
                picking_id=picking.id,
                location_id=location.id,
                package_id=package.id,
                action_name="package_not_in_picking",
                success=False,
            )

        updated_count = self.apply_location_to_package(move_lines, location)
        serial_progress = self.get_incoming_serial_progress(picking, package)

        if serial_progress["remaining_quantity"]:
            return self.build_scan_result(
                "package",
                _("Pallet"),
                _("Pallet %s updated to %s. Please scan a serial-tracked product.") % (package.name, location.display_name),
                barcode=code,
                picking_id=picking.id,
                location_id=location.id,
                package_id=package.id,
                action_name="update_package_location",
                updated_move_line_ids=move_lines.ids,
                success=True,
                next_step="scan_serial_product",
            )

        package_lines = picking.move_line_ids.filtered(lambda line: line.result_package_id)
        all_updated = bool(package_lines) and all(package_lines.mapped("is_location_updated"))

        if all_updated:
            next_step = "validate"
            message = _("All pallets updated. Please validate incoming picking.")
        else:
            next_step = "scan_package"
            message = _("Pallet %s updated to %s. Move lines: %s") % (
                package.name, location.display_name, updated_count
            )

        return self.build_scan_result(
            "package",
            _("Pallet"),
            message,
            barcode=code,
            picking_id=picking.id,
            location_id=location.id,
            package_id=False,
            action_name="update_package_location",
            updated_move_line_ids=move_lines.ids,
            success=True,
            next_step=next_step,
        )

    @api.model
    def process_incoming_serial_context_scan(self, code, picking_id=False, current_location_id=False, current_package_id=False, current_product_id=False):
        picking = self.env["stock.picking"].sudo().search([
            ("id", "=", picking_id),
            ("picking_type_id.code", "=", "incoming"),
            ("state", "not in", ("done", "cancel")),
        ], limit=1)
        package = self.env["stock.quant.package"].sudo().search([("id", "=", current_package_id)], limit=1)
        location = self.env["stock.location"].sudo().search([
            ("id", "=", current_location_id),
            ("usage", "=", "internal"),
        ], limit=1)
        if not picking or not package or not location or not self.get_package_move_lines(picking, package):
            return self.build_scan_result(
                "error",
                _("Error"),
                _("Please scan an incoming picking, location, and pallet first."),
                barcode=code,
                picking_id=picking_id,
                location_id=current_location_id,
                action_name="missing_serial_context",
                success=False,
            )
        if current_product_id:
            return self.process_incoming_serial_scan(
                code,
                picking=picking,
                location=location,
                package=package,
                current_product_id=current_product_id,
            )
        return self.process_incoming_serial_product_scan(code, picking, location, package)

    @api.model
    def process_incoming_serial_product_scan(self, code, picking, location, package):
        product = self.get_incoming_product_from_barcode(code)
        if len(product) > 1:
            return self.build_scan_result(
                "error",
                _("Error"),
                _("Product barcode matched multiple products: %s") % code,
                barcode=code,
                picking_id=picking.id,
                location_id=location.id,
                package_id=package.id,
                action_name="product_multiple_matches",
                success=False,
                next_step="scan_serial_product",
            )
        if not product or product.tracking != "serial":
            return self.build_scan_result(
                "error",
                _("Error"),
                _("Please scan a serial-tracked product on the current pallet."),
                barcode=code,
                picking_id=picking.id,
                location_id=location.id,
                package_id=package.id,
                action_name="serial_product_not_found",
                success=False,
                next_step="scan_serial_product",
            )
        if not self.get_pending_incoming_serial_move_lines(picking, package, product):
            return self.build_scan_result(
                "error",
                _("Error"),
                _("Product %s has no remaining serial quantity on pallet %s.") % (product.display_name, package.name),
                barcode=code,
                picking_id=picking.id,
                location_id=location.id,
                package_id=package.id,
                action_name="serial_product_completed",
                success=False,
                next_step="scan_serial_product",
            )
        return self.build_scan_result(
            "product",
            _("Product"),
            _("Product %s selected. Please scan serial number.") % product.display_name,
            barcode=code,
            picking_id=picking.id,
            location_id=location.id,
            package_id=package.id,
            product_id=product.id,
            action_name="select_serial_product",
            success=True,
            next_step="scan_serial",
        )

    @api.model
    def process_incoming_serial_scan(self, code, picking, location, package, current_product_id=False):
        product = self.env["product.product"].sudo().search([
            ("id", "=", current_product_id),
            ("tracking", "=", "serial"),
        ], limit=1)
        if not product:
            return self.build_scan_result(
                "error",
                _("Error"),
                _("Please scan a serial-tracked product first."),
                barcode=code,
                picking_id=picking.id,
                location_id=location.id,
                package_id=package.id,
                action_name="missing_serial_product",
                success=False,
                next_step="scan_serial_product",
            )
        serial_numbers = [value.strip() for value in code.replace("，", ",").replace("\r", "\n").replace("\n", ",").split(",") if value.strip()]
        if not serial_numbers:
            return self.build_scan_result(
                "error",
                _("Error"),
                _("Please scan at least one serial number."),
                barcode=code,
                picking_id=picking.id,
                location_id=location.id,
                package_id=package.id,
                product_id=product.id,
                action_name="missing_serial_number",
                success=False,
                next_step="scan_serial",
            )
        if len(serial_numbers) != len(set(serial_numbers)):
            return self.build_scan_result(
                "error",
                _("Error"),
                _("The same serial number cannot be included more than once in one scan."),
                barcode=code,
                picking_id=picking.id,
                location_id=location.id,
                package_id=package.id,
                product_id=product.id,
                action_name="serial_duplicate_in_batch",
                success=False,
                next_step="scan_serial",
            )
        pending_lines = self.get_pending_incoming_serial_move_lines(picking, package, product)
        if not pending_lines:
            return self.build_scan_result(
                "error",
                _("Error"),
                _("All serial numbers for product %s are already scanned.") % product.display_name,
                barcode=code,
                picking_id=picking.id,
                location_id=location.id,
                package_id=package.id,
                action_name="serial_product_completed",
                success=False,
                next_step="scan_serial_product",
            )
        rounding = product.uom_id.rounding
        pending_quantity = sum(pending_lines.mapped("quantity"))
        if float_compare(pending_quantity, float(len(serial_numbers)), precision_rounding=rounding) < 0:
            return self.build_scan_result(
                "error",
                _("Error"),
                _("Scanned serial number count %s exceeds remaining quantity %s for product %s on pallet %s.") % (
                    len(serial_numbers), pending_quantity, product.display_name, package.name
                ),
                barcode=code,
                picking_id=picking.id,
                location_id=location.id,
                package_id=package.id,
                product_id=product.id,
                action_name="serial_batch_exceeds_remaining",
                success=False,
                next_step="scan_serial",
            )
        serial_lot_values = []
        for serial_number in serial_numbers:
            duplicate_lines = self.env["stock.move.line"].sudo().search([
                ("picking_id", "=", picking.id),
                ("product_id", "=", product.id),
                "|",
                ("lot_id.name", "=", serial_number),
                ("lot_name", "=", serial_number),
            ], limit=1)
            if duplicate_lines:
                return self.build_scan_result(
                    "error",
                    _("Error"),
                    _("Serial number %s is already scanned on this incoming picking.") % serial_number,
                    barcode=code,
                    picking_id=picking.id,
                    location_id=location.id,
                    package_id=package.id,
                    product_id=product.id,
                    action_name="serial_duplicate_in_picking",
                    success=False,
                    next_step="scan_serial",
                )
            lots = self.env["stock.lot"].sudo().search([
                ("name", "=", serial_number),
                ("product_id", "=", product.id),
                ("company_id", "=", picking.company_id.id),
            ], limit=2)
            if len(lots) > 1:
                return self.build_scan_result(
                    "error",
                    _("Error"),
                    _("Serial number matched multiple records for product %s: %s") % (product.display_name, serial_number),
                    barcode=code,
                    picking_id=picking.id,
                    location_id=location.id,
                    package_id=package.id,
                    product_id=product.id,
                    action_name="serial_multiple_matches",
                    success=False,
                    next_step="scan_serial",
                )
            lot = lots[:1]
            if lot:
                positive_quant = self.env["stock.quant"].sudo().search([
                    ("lot_id", "=", lot.id),
                    ("company_id", "=", picking.company_id.id),
                    ("location_id.usage", "in", ("internal", "transit", "customer")),
                    ("quantity", ">", 0),
                ], limit=1)
                if positive_quant:
                    return self.build_scan_result(
                        "error",
                        _("Error"),
                        _("Serial number %s already has stock in this company.") % serial_number,
                        barcode=code,
                        picking_id=picking.id,
                        location_id=location.id,
                        package_id=package.id,
                        product_id=product.id,
                        action_name="serial_has_existing_stock",
                        success=False,
                        next_step="scan_serial",
                    )
            elif not picking.picking_type_id.use_create_lots:
                return self.build_scan_result(
                    "error",
                    _("Error"),
                    _("The incoming operation type must allow creating serial numbers."),
                    barcode=code,
                    picking_id=picking.id,
                    location_id=location.id,
                    package_id=package.id,
                    product_id=product.id,
                    action_name="serial_creation_not_allowed",
                    success=False,
                    next_step="scan_serial",
                )
            serial_lot_values.append((serial_number, lot))

        updated_move_line_ids = []
        for serial_number, lot in serial_lot_values:
            current_pending_lines = self.get_pending_incoming_serial_move_lines(picking, package, product)
            updated_line = self.apply_incoming_serial_scan(current_pending_lines[:1], serial_number, lot)
            updated_move_line_ids += updated_line.ids
        serial_progress = self.get_incoming_serial_progress(picking, package)
        current_progress = next(
            (item for item in serial_progress["products"] if item["product_id"] == product.id),
            {"remaining_quantity": 0.0},
        )
        package_lines = picking.move_line_ids.filtered(lambda line: line.result_package_id)
        all_updated = bool(package_lines) and all(package_lines.mapped("is_location_updated"))
        if current_progress["remaining_quantity"]:
            next_step = "scan_serial"
            package_id = package.id
            product_id = product.id
            message = (
                _("Serial number %s scanned for product %s. Please scan next serial number.") % (serial_numbers[0], product.display_name)
                if len(serial_numbers) == 1
                else _("Serial numbers %s scanned for product %s. Please scan next serial number.") % (", ".join(serial_numbers), product.display_name)
            )
        elif serial_progress["remaining_quantity"]:
            next_step = "scan_serial_product"
            package_id = package.id
            product_id = False
            message = _("Product %s serial numbers completed. Please scan next serial-tracked product.") % product.display_name
        elif all_updated:
            next_step = "validate"
            package_id = False
            product_id = False
            message = _("All pallets and serial numbers updated. Please validate incoming picking.")
        else:
            next_step = "scan_package"
            package_id = False
            product_id = False
            message = _("Pallet %s serial numbers completed. Please scan next pallet.") % package.name
        return self.build_scan_result(
            "serial",
            _("Serial Number"),
            message,
            barcode=code,
            picking_id=picking.id,
            location_id=location.id,
            package_id=package_id,
            product_id=product_id,
            action_name="scan_incoming_serial",
            updated_move_line_ids=updated_move_line_ids,
            success=True,
            next_step=next_step,
        )

    @api.model
    def get_picking_from_barcode(self, code):

        picking_model = self.env["stock.picking"]
        domain_base = [
            ("picking_type_id.code", "=", "incoming"),
            ("state", "not in", ("cancel",)),
        ]
        picking = picking_model.sudo().search(domain_base + [("name", "=", code)], limit=1)

        return picking

    @api.model
    def get_location_from_barcode(self, code):

        return self.env["stock.location"].sudo().search([
            ("barcode", "=", code),
            ("usage", "=", "internal"),
        ], limit=1)

    @api.model
    def get_package_from_barcode(self, code):

        package_model = self.env["stock.quant.package"]
        package = package_model.sudo().search([("barcode", "=", code)], limit=1)
        return package

    @api.model
    def get_incoming_product_from_barcode(self, code):
        product_model = self.env["product.product"]
        products = product_model.sudo().search([
            ("barcode", "=", code),
        ], limit=2)
        if not products:
            products = product_model.sudo().search([("name", "=", code)], limit=2)
        return products

    @api.model
    def get_package_move_lines(self, picking, package):

        return self.env["stock.move.line"].sudo().search([
            ("picking_id", "=", picking.id),
            ("result_package_id", "=", package.id),
        ])

    @api.model
    def get_pending_incoming_serial_move_lines(self, picking, package, product=False):
        lines = self.get_package_move_lines(picking, package).filtered(
            lambda line: line.product_id.tracking == "serial" and not line.lot_id and not line.lot_name and line.quantity > 0
        )
        return lines.filtered(lambda line: not product or line.product_id == product)

    @api.model
    def get_incoming_serial_progress(self, picking, package):
        serial_lines = self.get_package_move_lines(picking, package).filtered(
            lambda line: line.product_id.tracking == "serial" and line.quantity > 0
        )
        products = []
        total_quantity = 0.0
        scanned_quantity = 0.0
        for product in serial_lines.mapped("product_id"):
            product_lines = serial_lines.filtered(lambda line: line.product_id == product)
            product_total = sum(product_lines.mapped("quantity"))
            product_scanned = sum(product_lines.filtered(lambda line: line.lot_id or line.lot_name).mapped("quantity"))
            products.append({
                "product_id": product.id,
                "product_name": product.display_name,
                "total_quantity": product_total,
                "scanned_quantity": product_scanned,
                "remaining_quantity": max(product_total - product_scanned, 0.0),
            })
            total_quantity += product_total
            scanned_quantity += product_scanned
        return {
            "products": products,
            "total_quantity": total_quantity,
            "scanned_quantity": scanned_quantity,
            "remaining_quantity": max(total_quantity - scanned_quantity, 0.0),
        }

    @api.model
    def apply_incoming_serial_scan(self, move_lines, serial_number, lot=False):
        source_line = self.env["stock.move.line"].browse(move_lines[:1].id)
        rounding = source_line.product_uom_id.rounding or source_line.product_id.uom_id.rounding
        if float_compare(source_line.quantity, 1.0, precision_rounding=rounding) < 0:
            raise UserError(_("Serial-tracked product %s must be received in whole units.") % source_line.product_id.display_name)
        serial_values = {"lot_id": lot.id if lot else False, "lot_name": False if lot else serial_number}
        if float_compare(source_line.quantity, 1.0, precision_rounding=rounding) == 0:
            source_line.write(serial_values)
            return source_line
        source_line.write({"quantity": source_line.quantity - 1.0})
        serial_values.update({
            "picking_id": source_line.picking_id.id,
            "move_id": source_line.move_id.id,
            "product_id": source_line.product_id.id,
            "product_uom_id": source_line.product_uom_id.id,
            "quantity": 1.0,
            "location_id": source_line.location_id.id,
            "location_dest_id": source_line.location_dest_id.id,
            "result_package_id": source_line.result_package_id.id,
            "owner_id": source_line.owner_id.id,
            "inbound_order_product_pallet_id": source_line.inbound_order_product_pallet_id.id,
            "is_location_updated": source_line.is_location_updated,
            "location_updated_by_id": source_line.location_updated_by_id.id,
            "location_updated_datetime": source_line.location_updated_datetime,
        })
        return self.env["stock.move.line"].create(serial_values)

    @api.model
    def apply_location_to_package(self, move_lines, location):

        normal_move_lines = self.env["stock.move.line"].browse(move_lines.ids)
        normal_move_lines.write({
            "location_dest_id": location.id,
            "is_location_updated": True,
            "location_updated_by_id": self.env.user.id,
            "location_updated_datetime": fields.Datetime.now(),
        })
        return len(normal_move_lines)

    @api.model
    def get_incoming_scan_records(self, picking):
        for rec in self:
            if not picking:
                return {
                    "stock.picking": [],
                    "stock.move": [],
                    "stock.move.line": [],
                    "product.product": [],
                    "stock.location": [],
                    "stock.quant.package": [],
                    "stock.lot": [],
                    "uom.uom": [],
                }
            move_lines = picking.move_line_ids
            products = picking.move_ids.product_id | move_lines.product_id
            locations = picking.location_id | picking.location_dest_id | move_lines.location_id | move_lines.location_dest_id
            packages = move_lines.result_package_id | move_lines.package_id
            lots = move_lines.lot_id
            uoms = products.uom_id | move_lines.product_uom_id
            return {
                "stock.picking": picking.sudo().read([
                    "id", "name", "origin", "partner_id", "state", "picking_type_code", "location_id", "location_dest_id", "ref_1",
                ], load=False),
                "stock.move": picking.move_ids.sudo().read([
                    "id", "name", "product_id", "product_uom_qty", "quantity", "product_uom", "state", "picking_id",
                ], load=False),
                "stock.move.line": move_lines.sudo().read([
                    "id", "picking_id", "move_id", "product_id", "quantity", "product_uom_id",
                    "location_id", "location_dest_id", "lot_id", "lot_name", "package_id", "result_package_id",
                    "is_location_updated", "location_updated_by_id", "location_updated_datetime",
                ], load=False),
                "product.product": products.sudo().read([
                    "id", "display_name", "name", "barcode", "default_code", "uom_id", "tracking",
                ], load=False),
                "stock.location": locations.sudo().read([
                    "id", "name", "display_name", "barcode", "usage",
                ], load=False),
                "stock.quant.package": packages.sudo().read([
                    "id", "name", "barcode", "display_name",
                ], load=False),
                "stock.lot": lots.sudo().read([
                    "id", "name", "product_id",
                ], load=False),
                "uom.uom": uoms.sudo().read([
                    "id", "name",
                ], load=False),
            }
        return {}

    @api.model
    def get_incoming_scan_state(self, picking_id=False, current_location_id=False, last_scan=None, current_package_id=False, current_product_id=False):
        picking = self.env["stock.picking"].sudo().search([("id", "=", picking_id)], limit=1) if picking_id else self.env["stock.picking"]
        location = self.env["stock.location"].sudo().search([("id", "=", current_location_id)], limit=1) if current_location_id else self.env["stock.location"]
        package = self.env["stock.quant.package"].sudo().search([("id", "=", current_package_id)], limit=1) if current_package_id else self.env["stock.quant.package"]
        product = self.env["product.product"].sudo().search([("id", "=", current_product_id)], limit=1) if current_product_id else self.env["product.product"]

        if not picking:
            return {
                "picking": {},
                "current_location": self.format_location_for_scan_state(location),
                "current_pallet": self.format_package_for_incoming_scan_state(package),
                "current_product": self.format_product_for_incoming_scan_state(product),
                "serial_progress": {"products": [], "total_quantity": 0.0, "scanned_quantity": 0.0, "remaining_quantity": 0.0},
                "summary": {
                    "total_pallets": 0,
                    "updated_pallets": 0,
                    "pending_pallets": 0,
                    "total_move_lines": 0,
                    "updated_move_lines": 0,
                    "pending_move_lines": 0,
                },
                "pallets": [],
                "last_scan": last_scan or {},
            }
        is_picking_done = picking.state == "done"
        package_lines = picking.move_line_ids.filtered(lambda line: line.result_package_id)
        packages = package_lines.mapped("result_package_id")
        serial_progress = self.get_incoming_serial_progress(picking, package) if package else {"products": [], "total_quantity": 0.0, "scanned_quantity": 0.0, "remaining_quantity": 0.0}
        pallet_data = []
        updated_pallets = 0
        for package in packages:
            lines = package_lines.filtered(lambda line: line.result_package_id == package)
            is_location_updated = is_picking_done or (
                    bool(lines) and all(lines.mapped("is_location_updated"))
            )
            if is_location_updated:
                updated_pallets += 1
            pallet_location = lines[:1].location_dest_id if lines else self.env["stock.location"]
            products = []
            for line in lines:
                serial_scanned_quantity = line.quantity if line.product_id.tracking == "serial" and (line.lot_id or line.lot_name) else 0.0
                products.append({
                    "move_line_id": line.id,
                    "move_id": line.move_id.id,
                    "product_id": line.product_id.id,
                    "product_name": line.product_id.display_name,
                    "product_barcode": line.product_id.barcode or "",
                    "default_code": line.product_id.default_code or "",
                    "quantity": line.quantity,
                    "qty_done": serial_scanned_quantity if line.product_id.tracking == "serial" else line.quantity,
                    "tracking": line.product_id.tracking,
                    "serial_scanned_quantity": serial_scanned_quantity,
                    "serial_remaining_quantity": line.quantity - serial_scanned_quantity,
                    "uom": line.product_uom_id.name,
                    "lot": line.lot_id.name or line.lot_name or "",
                    "source_location": line.location_id.display_name,
                    "dest_location": line.location_dest_id.display_name,
                })
            pallet_data.append({
                "package_id": package.id,
                "package_name": package.name,
                "package_barcode": package.barcode or package.name,
                "location_id": pallet_location.id or False,
                "location_name": pallet_location.display_name or "",
                "is_location_updated": is_location_updated,
                "move_line_ids": lines.ids,
                "products": products,
            })

        total_pallets = len(packages)
        updated_move_lines = (
            len(package_lines)
            if is_picking_done
            else len(package_lines.filtered(lambda line: line.is_location_updated))
        )
        return {
            "picking": {
                "id": picking.id,
                "name": picking.name,
                "origin": picking.origin or "",
                "reference": picking.ref_1 or "",
                "partner": picking.partner_id.display_name or "",
                "state": picking.state,
                "picking_type_code": picking.picking_type_code,
            },
            "current_location": self.format_location_for_scan_state(location),
            "current_pallet": self.format_package_for_incoming_scan_state(package),
            "current_product": self.format_product_for_incoming_scan_state(product),
            "serial_progress": serial_progress,
            "summary": {
                "total_pallets": total_pallets,
                "updated_pallets": updated_pallets,
                "pending_pallets": total_pallets - updated_pallets,
                "total_move_lines": len(package_lines),
                "updated_move_lines": updated_move_lines,
                "pending_move_lines": len(package_lines) - updated_move_lines,
            },
            "pallets": pallet_data,
            "last_scan": last_scan or {},
        }

    @api.model
    def format_location_for_scan_state(self, location):
        if not location:
            return {}
        return {
            "id": location.id,
            "name": location.name,
            "barcode": location.barcode or "",
            "display_name": location.display_name,
        }

    @api.model
    def format_package_for_incoming_scan_state(self, package):
        if not package:
            return {}
        return {
            "id": package.id,
            "name": package.name,
            "barcode": package.barcode or package.name,
            "display_name": package.display_name,
        }

    @api.model
    def format_product_for_incoming_scan_state(self, product):
        if not product:
            return {}
        return {
            "id": product.id,
            "name": product.name,
            "display_name": product.display_name,
            "barcode": product.barcode or "",
            "default_code": product.default_code or "",
            "tracking": product.tracking,
        }

    @api.model
    def build_scan_result(self, result_type, barcode_type, message, barcode="",
                          picking_id=False, location_id=False, package_id=False, product_id=False,
                          action_name=False, updated_move_line_ids=None, success=True, next_step=False):

        #picking = rec.env["stock.picking"].sudo().search([("id", "=", picking_id)], limit=1) if picking_id else rec.env["stock.picking"]
        last_scan = {
            "barcode": barcode or "",
            "type": result_type,
            "barcode_type": barcode_type,
            "message": message,
            "updated_move_line_ids": updated_move_line_ids or [],
        }
        return {
            "success": success,
            "type": result_type,
            "barcode": barcode or "",
            "barcode_type": barcode_type,
            "message": message,
            "next_step": next_step or self.get_next_scan_step(result_type, picking_id, location_id),
            "current": {
                "picking_id": picking_id,
                "location_id": location_id,
                "package_id": package_id,
                "product_id": product_id,
            },
            "action": {
                "name": action_name or result_type,
                "updated_move_line_ids": updated_move_line_ids or [],
            },
            #"records": rec.get_incoming_scan_records(picking),
            "scan_state": self.get_incoming_scan_state(
                picking_id=picking_id,
                current_location_id=location_id,
                last_scan=last_scan,
                current_package_id=package_id,
                current_product_id=product_id,
            ),
        }

    @api.model
    def get_next_scan_step(self, result_type, picking_id=False, location_id=False):
        if not picking_id:
            return "scan_picking"
        if not location_id:
            return "scan_location"
        if result_type == "location":
            return "scan_package"
        return "scan_package"
