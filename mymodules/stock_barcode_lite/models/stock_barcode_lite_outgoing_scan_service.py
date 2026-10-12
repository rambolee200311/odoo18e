# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.tools.float_utils import float_compare


class StockBarcodeLiteOutgoingScanService(models.AbstractModel):
    _inherit = "stock.barcode.lite.scan.service"

    OUTGOING_OPERATION_CODES = {
        "OUT:PICKING": "picking",
        "OUT:LOCATION": "location",
        "OUT:PALLET": "pallet",
        "OUT:PRODUCT": "product",
        "OUT:LOT": "lot",
        "OUT:SN": "serial",
        "OUT:QTY": "quantity",
    }
    OUTGOING_OPERATIONS = set(OUTGOING_OPERATION_CODES.values())

    @api.model
    def process_outgoing_scan_barcode(
        self,
        code,
        picking_id=False,
        current_location_id=False,
        current_package_id=False,
        current_product_id=False,
        current_lot_id=False,
        pending_operation=False,
        quantity=False,
    ):
        code = (code or "").strip()
        pending_operation = self.normalize_outgoing_operation(pending_operation)
        quantity_provided = quantity not in (False, None, "")

        if not code and not quantity_provided:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Please scan a barcode."),
                barcode=code,
                picking_id=picking_id,
                location_id=current_location_id,
                package_id=current_package_id,
                product_id=current_product_id,
                lot_id=current_lot_id,
                pending_operation=pending_operation,
                action_name="scan_error",
                success=False,
            )

        operation = self.OUTGOING_OPERATION_CODES.get((code or "").strip().upper())
        if operation:
            current = self.clean_outgoing_context_for_operation(
                operation,
                picking_id=picking_id,
                current_location_id=current_location_id,
                current_package_id=current_package_id,
                current_product_id=current_product_id,
                current_lot_id=current_lot_id,
            )
            return self.build_outgoing_scan_result(
                "operation",
                _("Operation"),
                _("Next barcode will be processed as %s.") % operation,
                barcode=code,
                picking_id=current["picking_id"],
                location_id=current["location_id"],
                package_id=current["package_id"],
                product_id=current["product_id"],
                lot_id=current["lot_id"],
                pending_operation=operation,
                action_name="set_operation",
                success=True,
            )

        operation = pending_operation or self.infer_outgoing_operation(
            picking_id=picking_id,
            current_location_id=current_location_id,
            current_package_id=current_package_id,
            current_product_id=current_product_id,
            current_lot_id=current_lot_id,
            quantity=quantity,
        )

        if operation == "picking":
            return self.process_outgoing_picking_scan(code, pending_operation=pending_operation)
        if operation == "location":
            return self.process_outgoing_location_scan(
                code,
                picking_id=picking_id,
                current_location_id=current_location_id,
                current_package_id=current_package_id,
                current_product_id=current_product_id,
                current_lot_id=current_lot_id,
                pending_operation=pending_operation,
            )
        if operation == "pallet":
            return self.process_outgoing_pallet_scan(
                code,
                picking_id=picking_id,
                current_location_id=current_location_id,
                pending_operation=pending_operation,
            )
        if operation == "product":
            return self.process_outgoing_product_scan(
                code,
                picking_id=picking_id,
                current_location_id=current_location_id,
                current_package_id=current_package_id,
                pending_operation=pending_operation,
            )
        if operation == "lot":
            return self.process_outgoing_lot_scan(
                code,
                picking_id=picking_id,
                current_location_id=current_location_id,
                current_package_id=current_package_id,
                current_product_id=current_product_id,
                pending_operation=pending_operation,
            )
        if operation == "serial":
            return self.process_outgoing_serial_scan(
                code,
                picking_id=picking_id,
                current_location_id=current_location_id,
                current_package_id=current_package_id,
                current_product_id=current_product_id,
                pending_operation=pending_operation,
            )
        if operation == "quantity":
            return self.process_outgoing_quantity_scan(
                code,
                quantity=quantity,
                picking_id=picking_id,
                current_location_id=current_location_id,
                current_package_id=current_package_id,
                current_product_id=current_product_id,
                current_lot_id=current_lot_id,
                pending_operation=pending_operation,
            )
        if operation == "location_or_pallet":
            location = self.get_outgoing_location_from_barcode(code)
            if location:
                return self.process_outgoing_location_scan(
                    code,
                    picking_id=picking_id,
                    current_location_id=current_location_id,
                    current_package_id=current_package_id,
                    current_product_id=current_product_id,
                    current_lot_id=current_lot_id,
                    pending_operation=False,
                )
            return self.process_outgoing_pallet_scan(
                code,
                picking_id=picking_id,
                current_location_id=current_location_id,
                pending_operation=False,
            )

        return self.build_outgoing_scan_result(
            "error",
            _("Error"),
            _("Barcode not recognized: %s") % code,
            barcode=code,
            picking_id=picking_id,
            location_id=current_location_id,
            package_id=current_package_id,
            product_id=current_product_id,
            lot_id=current_lot_id,
            pending_operation=pending_operation,
            action_name="barcode_not_found",
            success=False,
        )

    @api.model
    def process_outgoing_picking_scan(self, code, pending_operation=False):
        picking = self.get_outgoing_picking_from_barcode(code)
        if not picking:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Please scan an outgoing picking first."),
                barcode=code,
                pending_operation=pending_operation,
                action_name="missing_picking",
                success=False,
            )
        if picking.state == "done":
            return self.build_outgoing_scan_result(
                "picking",
                _("Outgoing Picking"),
                _("Outgoing picking %s is completed. Read-only view.") % picking.name,
                barcode=code,
                picking_id=picking.id,
                pending_operation=False,
                action_name="view_completed_picking",
                success=True,
                next_step="completed",
            )
        return self.build_outgoing_scan_result(
            "picking",
            _("Outgoing Picking"),
            _("Outgoing picking %s selected.") % picking.name,
            barcode=code,
            picking_id=picking.id,
            pending_operation=False,
            action_name="select_picking",
            success=True,
        )

    @api.model
    def process_outgoing_location_scan(
        self,
        code,
        picking_id=False,
        current_location_id=False,
        current_package_id=False,
        current_product_id=False,
        current_lot_id=False,
        pending_operation=False,
    ):
        if not picking_id:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Please scan outgoing picking first."),
                barcode=code,
                location_id=current_location_id,
                package_id=current_package_id,
                product_id=current_product_id,
                lot_id=current_lot_id,
                pending_operation=pending_operation,
                action_name="missing_picking",
                success=False,
            )
        location = self.get_outgoing_location_from_barcode(code)
        if not location:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Location not found: %s") % code,
                barcode=code,
                picking_id=picking_id,
                location_id=current_location_id,
                package_id=current_package_id,
                product_id=current_product_id,
                lot_id=current_lot_id,
                pending_operation=pending_operation,
                action_name="location_not_found",
                success=False,
            )
        return self.build_outgoing_scan_result(
            "location",
            _("Location"),
            _("Current location changed to %s.") % location.display_name,
            barcode=code,
            picking_id=picking_id,
            location_id=location.id,
            package_id=current_package_id,
            product_id=current_product_id,
            lot_id=current_lot_id,
            pending_operation=False,
            action_name="select_location",
            success=True,
        )

    @api.model
    def process_outgoing_pallet_scan(self, code, picking_id=False, current_location_id=False, pending_operation=False):
        picking = self.get_valid_outgoing_picking(picking_id)
        if not picking:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Done, cancelled, missing, or invalid outgoing picking cannot be scanned."),
                barcode=code,
                picking_id=picking_id,
                location_id=current_location_id,
                pending_operation=pending_operation,
                action_name="invalid_picking",
                success=False,
            )
        if not current_location_id:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Please scan location before pallet."),
                barcode=code,
                picking_id=picking.id,
                pending_operation=False,
                action_name="missing_location",
                success=False,
                next_step="scan_location",
            )

        package = self.get_outgoing_package_from_barcode(code)
        if not package:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Pallet not found: %s") % code,
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                pending_operation=pending_operation,
                action_name="pallet_not_found",
                success=False,
            )

        move_lines = self.get_outgoing_package_move_lines(picking, package)
        if not move_lines and not picking.is_unspecified_pallet_outgoing:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Pallet %s is not specified on current outgoing picking.") % (package.name or package.barcode),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=False,
                product_id=False,
                lot_id=False,
                pending_operation=pending_operation,
                next_step="scan_pallet",
                action_name="pallet_not_in_picking",
                success=False,
            )

        if move_lines and not picking.is_unspecified_pallet_outgoing and self.are_outgoing_lines_completed(move_lines):
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Pallet %s is already scanned.") % (package.name or package.barcode),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                pending_operation=False,
                action_name="pallet_already_scanned",
                success=False,
            )

        stock_data = self.get_package_stock_set(package)
        if not stock_data["lines"]:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Pallet %s has no internal stock.") % (package.name or package.barcode),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=False,
                product_id=False,
                lot_id=False,
                pending_operation=pending_operation,
                next_step="scan_pallet",
                action_name="pallet_no_stock",
                success=False,
            )
        if len(stock_data["location_ids"]) > 1:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Pallet %s is stored in multiple internal locations; please consolidate it first.")
                % (package.name or package.barcode),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=False,
                product_id=False,
                lot_id=False,
                pending_operation=pending_operation,
                next_step="scan_pallet",
                action_name="pallet_multiple_locations",
                success=False,
            )

        if picking.is_unspecified_pallet_outgoing:
            if stock_data["location"].id != current_location_id:
                return self.build_outgoing_scan_result(
                    "error",
                    _("Error"),
                    _("Pallet %s must be scanned from location %s.") % (package.name or package.barcode, stock_data["location"].display_name),
                    barcode=code,
                    picking_id=picking.id,
                    location_id=current_location_id,
                    package_id=False,
                    product_id=False,
                    lot_id=False,
                    pending_operation=pending_operation,
                    next_step="scan_pallet",
                    action_name="pallet_location_mismatch",
                    success=False,
                )
            source_location = self.env["stock.location"].sudo().search([
                ("id", "=", stock_data["location"].id),
                ("id", "child_of", picking.location_id.id),
                ("usage", "=", "internal"),
            ], limit=1)
            if not source_location:
                return self.build_outgoing_scan_result(
                    "error",
                    _("Error"),
                    _("Pallet %s is outside the source location of this outgoing picking.") % (package.name or package.barcode),
                    barcode=code,
                    picking_id=picking.id,
                    location_id=current_location_id,
                    package_id=False,
                    product_id=False,
                    lot_id=False,
                    pending_operation=pending_operation,
                    next_step="scan_pallet",
                    action_name="pallet_outside_source_location",
                    success=False,
                )
            return self.build_outgoing_scan_result(
                "pallet",
                _("Pallet"),
                _("Pallet %s selected for partial picking. Please scan product.") % (package.name or package.barcode),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                pending_operation=False,
                next_step="scan_product",
                action_name="select_unspecified_partial_pallet",
                success=True,
            )

        has_untracked_serial_stock = self.has_untracked_serial_stock(stock_data["quants"])
        if has_untracked_serial_stock and picking.outbound_scan_mode == "whole_pallet":
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("This pallet contains serial-tracked stock without SN. Please use partial pallet picking."),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                pending_operation=False,
                next_step="scan_pallet",
                action_name="whole_pallet_missing_serial",
                success=False,
            )

        can_whole, reason = self.can_ship_whole_package(picking, package)
        if has_untracked_serial_stock:
            can_whole = False
            reason = _("This pallet contains serial-tracked stock without SN.")
        if can_whole:
            updated_lines = self.apply_whole_package_scan(move_lines, stock_data["location"])

            move_line_model = self.env["stock.move.line"]
            picking_lines = move_line_model.sudo().search([
                ("picking_id", "=", picking.id),
                ("package_id", "!=", False),
                ("quantity", ">", 0),
            ], order="id")
            picking_done = self.are_outgoing_lines_completed(picking_lines)

            if picking_done:
                next_step = "validate"
                message = _("All products scanned. Please validate outgoing picking.")
            else:
                next_step = "scan_pallet"
                message = _("Pallet %s scanned as whole pallet. Please scan next pallet.") % (
                        package.name or package.barcode
                )

            return self.build_outgoing_scan_result(
                "pallet",
                _("Pallet"),
                message,
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=False,
                product_id=False,
                lot_id=False,
                pending_operation=False,
                next_step=next_step,
                action_name="scan_whole_pallet",
                updated_move_line_ids=updated_lines.ids,
                success=True,
            )

        return self.build_outgoing_scan_result(
            "pallet",
            _("Pallet"),
            _("Pallet %s selected for partial picking. %s") % (package.name or package.barcode, reason),
            barcode=code,
            picking_id=picking.id,
            location_id=current_location_id,
            package_id=package.id,
            pending_operation=False,
            action_name="select_partial_pallet",
            success=True,
        )

    @api.model
    def process_outgoing_product_scan(
        self,
        code,
        picking_id=False,
        current_location_id=False,
        current_package_id=False,
        pending_operation=False,
    ):
        picking = self.get_valid_outgoing_picking(picking_id)
        package = self.env["stock.quant.package"].sudo().browse(current_package_id) if current_package_id else self.env["stock.quant.package"]
        if not picking or not package:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Please scan outgoing picking and pallet first."),
                barcode=code,
                picking_id=picking_id,
                location_id=current_location_id,
                package_id=current_package_id,
                pending_operation=pending_operation,
                action_name="missing_picking_or_pallet",
                success=False,
            )

        product = self.get_outgoing_product_from_barcode(code)
        if len(product) > 1:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Product barcode matched multiple products: %s") % code,
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                pending_operation=pending_operation,
                action_name="product_multiple_matches",
                success=False,
            )
        if not product:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Product not found: %s") % code,
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                pending_operation=pending_operation,
                action_name="product_not_found",
                success=False,
            )

        if picking.is_unspecified_pallet_outgoing:
            _moves, _remaining_by_move, remaining_qty = self.get_unspecified_pallet_outgoing_demand(picking, product)
            stock_data = self.get_package_stock_set(package)
            package_available_qty = sum(
                stock_line["available_quantity"]
                for stock_key, stock_line in stock_data["lines"].items()
                if stock_key[0] == product.id
            )
            if float_compare(remaining_qty, 0.0, precision_rounding=product.uom_id.rounding) <= 0:
                return self.build_outgoing_scan_result(
                    "error",
                    _("Error"),
                    _("Product %s has no remaining demand on this outgoing picking.") % product.display_name,
                    barcode=code,
                    picking_id=picking.id,
                    location_id=current_location_id,
                    package_id=package.id,
                    product_id=False,
                    lot_id=False,
                    pending_operation=pending_operation,
                    next_step="scan_product",
                    action_name="product_no_remaining_demand",
                    success=False,
                )
            if float_compare(package_available_qty, 0.0, precision_rounding=product.uom_id.rounding) <= 0:
                return self.build_outgoing_scan_result(
                    "error",
                    _("Error"),
                    _("Product %s has no available stock on pallet %s.") % (product.display_name, package.name or package.barcode),
                    barcode=code,
                    picking_id=picking.id,
                    location_id=current_location_id,
                    package_id=package.id,
                    product_id=False,
                    lot_id=False,
                    pending_operation=pending_operation,
                    next_step="scan_product",
                    action_name="product_not_on_pallet",
                    success=False,
                )
            lines = self.env["stock.move.line"]
        else:
            lines = self.get_pending_outgoing_move_lines(picking, package, product)
        if not lines and not picking.is_unspecified_pallet_outgoing:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Product %s has no remaining demand on pallet %s.")
                % (product.display_name, package.name or package.barcode),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=False,
                lot_id=False,
                pending_operation=pending_operation,
                next_step="scan_product",
                action_name="product_not_in_pallet_demand",
                success=False,
            )

        lot_id = False
        if product.tracking == "serial":
            next_step = "scan_serial"
            message = _("Product %s selected. Please scan serial number.") % product.display_name
        elif product.tracking == "lot":
            next_step = "scan_lot"
            message = _("Product %s selected. Please scan lot.") % product.display_name
        else:
            next_step = "input_quantity"
            message = _("Product %s selected. Please input quantity.") % product.display_name
        return self.build_outgoing_scan_result(
            "product",
            _("Product"),
            message,
            barcode=code,
            picking_id=picking.id,
            location_id=current_location_id,
            package_id=package.id,
            product_id=product.id,
            lot_id=lot_id,
            pending_operation=False,
            next_step=next_step,
            action_name="select_product",
            success=True,
        )

    @api.model
    def process_outgoing_lot_scan(
        self,
        code,
        picking_id=False,
        current_location_id=False,
        current_package_id=False,
        current_product_id=False,
        pending_operation=False,
    ):
        picking = self.get_valid_outgoing_picking(picking_id)
        package = self.env["stock.quant.package"].sudo().browse(current_package_id) if current_package_id else self.env["stock.quant.package"]
        product = self.env["product.product"].sudo().browse(current_product_id) if current_product_id else self.env["product.product"]
        if product and product.tracking == "serial":
            return self.process_outgoing_serial_scan(
                code,
                picking_id=picking_id,
                current_location_id=current_location_id,
                current_package_id=current_package_id,
                current_product_id=current_product_id,
                pending_operation=pending_operation,
            )
        if not picking or not package or not product:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Please scan outgoing picking, pallet, and product first."),
                barcode=code,
                picking_id=picking_id,
                location_id=current_location_id,
                package_id=current_package_id,
                product_id=current_product_id,
                pending_operation=pending_operation,
                action_name="missing_lot_context",
                success=False,
            )

        lot = self.env["stock.lot"].sudo().search([
            ("name", "=", code),
            ("product_id", "=", product.id),
        ], limit=2)
        if len(lot) > 1:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Lot barcode matched multiple lots for product %s: %s") % (product.display_name, code),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                lot_id=False,
                pending_operation=pending_operation,
                next_step="scan_lot",
                action_name="lot_multiple_matches",
                success=False,
            )
        if not lot:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Lot not found for product %s: %s") % (product.display_name, code),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                lot_id=False,
                pending_operation=pending_operation,
                next_step="scan_lot",
                action_name="lot_not_found",
                success=False,
            )

        if picking.is_unspecified_pallet_outgoing:
            _moves, _remaining_by_move, remaining_qty = self.get_unspecified_pallet_outgoing_demand(picking, product)
            lines = self.env["stock.move.line"]
        else:
            lines = self.get_pending_outgoing_move_lines(picking, package, product, lot)
            remaining_qty = 0.0
        if (picking.is_unspecified_pallet_outgoing and float_compare(remaining_qty, 0.0, precision_rounding=product.uom_id.rounding) <= 0) or (not picking.is_unspecified_pallet_outgoing and not lines):
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Lot %s has no remaining demand for product %s on pallet %s.")
                % (lot.name, product.display_name, package.name or package.barcode),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                lot_id=False,
                pending_operation=pending_operation,
                next_step="scan_lot",
                action_name="lot_not_in_pallet_demand",
                success=False,
            )

        return self.build_outgoing_scan_result(
            "lot",
            _("Lot"),
            _("Lot %s selected. Please input quantity.") % lot.name,
            barcode=code,
            picking_id=picking.id,
            location_id=current_location_id,
            package_id=package.id,
            product_id=product.id,
            lot_id=lot.id,
            pending_operation=False,
            next_step="input_quantity",
            action_name="select_lot",
            success=True,
        )

    @api.model
    def process_outgoing_serial_scan(
        self,
        code,
        picking_id=False,
        current_location_id=False,
        current_package_id=False,
        current_product_id=False,
        pending_operation=False,
    ):
        picking = self.get_valid_outgoing_picking(picking_id)
        package = self.env["stock.quant.package"].sudo().browse(current_package_id) if current_package_id else self.env["stock.quant.package"]
        product = self.env["product.product"].sudo().browse(current_product_id) if current_product_id else self.env["product.product"]
        if not picking or not package or not product or product.tracking != "serial":
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Please scan outgoing picking, pallet, and serial-tracked product first."),
                barcode=code,
                picking_id=picking_id,
                location_id=current_location_id,
                package_id=current_package_id,
                product_id=current_product_id,
                pending_operation=pending_operation,
                action_name="missing_serial_context",
                success=False,
            )
        if picking.is_unspecified_pallet_outgoing:
            return self.process_unspecified_pallet_outgoing_serial_scan(
                code,
                picking,
                package,
                product,
                current_location_id,
            )
        stock_data = self.get_package_stock_set(package)
        if len(stock_data["location_ids"]) != 1 or not stock_data["location"]:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Pallet %s must have stock in exactly one internal location.") % (package.name or package.barcode),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                action_name="serial_pallet_multiple_locations",
                success=False,
                next_step="scan_serial",
            )
        stock_location = stock_data["location"]
        if stock_location.id != current_location_id:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Serial number must be scanned from location %s.") % stock_location.display_name,
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                action_name="serial_location_mismatch",
                success=False,
                next_step="scan_serial",
            )
        pending_lines = self.get_pending_outgoing_move_lines(picking, package, product)
        if not pending_lines:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Product %s has no remaining demand on pallet %s.") % (product.display_name, package.name or package.barcode),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                action_name="serial_product_completed",
                success=False,
                next_step="scan_product",
            )
        lots = self.env["stock.lot"].sudo().search([
            ("name", "=", code),
            ("product_id", "=", product.id),
            ("company_id", "=", picking.company_id.id),
        ], limit=2)
        if len(lots) > 1:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Serial number matched multiple records for product %s: %s") % (product.display_name, code),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                action_name="serial_multiple_matches",
                success=False,
                next_step="scan_serial",
            )
        if not lots:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Serial number not found for product %s: %s") % (product.display_name, code),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                action_name="serial_not_found",
                success=False,
                next_step="scan_serial",
            )
        lot = lots[:1]
        move_line_model = self.env["stock.move.line"]
        quant_model = self.env["stock.quant"]
        duplicate_line = move_line_model.sudo().search([
            ("picking_id", "=", picking.id),
            ("product_id", "=", product.id),
            ("lot_id", "=", lot.id),
            ("outbound_scanned_quantity", ">", 0),
        ], limit=1)
        if duplicate_line:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Serial number %s is already scanned on this outgoing picking.") % code,
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                action_name="serial_duplicate_in_picking",
                success=False,
                next_step="scan_serial",
            )
        source_lines = self.get_pending_outgoing_move_lines(picking, package, product, lot).filtered(
            lambda line: line.location_id == stock_location
        )
        if not source_lines:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Serial number %s is not required on the current pallet.") % code,
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                action_name="serial_not_in_pallet_demand",
                success=False,
                next_step="scan_serial",
            )
        source_line = source_lines[:1]
        source_quants = quant_model.sudo().search([
            ("package_id", "=", package.id),
            ("product_id", "=", product.id),
            ("lot_id", "=", lot.id),
            ("location_id", "=", stock_location.id),
            ("owner_id", "=", source_line.owner_id.id or False),
            ("quantity", ">", 0),
        ])
        available_quantity = sum(max(quant.quantity - quant.reserved_quantity, 0.0) for quant in source_quants)
        if float_compare(available_quantity, 1.0, precision_rounding=product.uom_id.rounding) < 0:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Serial number %s is not available on the current pallet.") % code,
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                action_name="serial_not_available",
                success=False,
                next_step="scan_serial",
            )

        source_line = move_line_model.browse(source_line.id)
        rounding = source_line.product_uom_id.rounding or product.uom_id.rounding
        if float_compare(source_line.quantity, 1.0, precision_rounding=rounding) < 0:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Serial-tracked product %s must be picked in whole units.") % product.display_name,
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                action_name="serial_invalid_quantity",
                success=False,
                next_step="scan_serial",
            )
        if source_line.lot_id and float_compare(source_line.quantity, 1.0, precision_rounding=rounding) != 0:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Serial number %s must have exactly one unit on the outgoing picking.") % code,
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                action_name="serial_tracked_quantity_invalid",
                success=False,
                next_step="scan_serial",
            )
        now = fields.Datetime.now()
        serial_values = {
            "lot_id": lot.id,
            "lot_name": False,
            "location_id": stock_location.id,
            "is_outbound_scanned": True,
            "outbound_scanned_quantity": 1.0,
            "outbound_scanned_by_id": self.env.user.id,
            "outbound_scanned_datetime": now,
        }
        if float_compare(source_line.quantity, 1.0, precision_rounding=rounding) == 0:
            source_line.write(serial_values)
            updated_line = source_line
        else:
            source_line.write({"quantity": source_line.quantity - 1.0})
            serial_values.update({
                "picking_id": source_line.picking_id.id,
                "move_id": source_line.move_id.id,
                "product_id": product.id,
                "product_uom_id": source_line.product_uom_id.id,
                "quantity": 1.0,
                "location_dest_id": source_line.location_dest_id.id,
                "package_id": source_line.package_id.id,
                "result_package_id": source_line.result_package_id.id,
                "owner_id": source_line.owner_id.id,
            })
            updated_line = move_line_model.create(serial_values)

        package_lines = self.get_outgoing_package_move_lines(picking, package)
        picking_lines = move_line_model.sudo().search([
            ("picking_id", "=", picking.id),
            ("package_id", "!=", False),
            ("quantity", ">", 0),
        ], order="id")
        product_pending = self.get_pending_outgoing_move_lines(picking, package, product)
        if self.are_outgoing_lines_completed(picking_lines):
            next_step = "validate"
            package_id = False
            product_id = False
            message = _("All products scanned. Please validate outgoing picking.")
        elif self.are_outgoing_lines_completed(package_lines):
            next_step = "scan_pallet"
            package_id = False
            product_id = False
            message = _("Pallet %s completed. Please scan next pallet.") % (package.name or package.barcode)
        elif product_pending:
            next_step = "scan_serial"
            package_id = package.id
            product_id = product.id
            message = _("Serial number %s scanned. Please scan next serial number.") % code
        else:
            next_step = "scan_product"
            package_id = package.id
            product_id = False
            message = _("Product %s completed. Please scan next product.") % product.display_name
        return self.build_outgoing_scan_result(
            "serial",
            _("Serial Number"),
            message,
            barcode=code,
            picking_id=picking.id,
            location_id=current_location_id,
            package_id=package_id,
            product_id=product_id,
            lot_id=False,
            pending_operation=False,
            next_step=next_step,
            action_name="scan_partial_serial",
            updated_move_line_ids=updated_line.ids,
            success=True,
        )

    @api.model
    def process_outgoing_quantity_scan(
        self,
        code,
        quantity=False,
        picking_id=False,
        current_location_id=False,
        current_package_id=False,
        current_product_id=False,
        current_lot_id=False,
        pending_operation=False,
    ):
        picking = self.get_valid_outgoing_picking(picking_id)
        package = self.env["stock.quant.package"].sudo().browse(current_package_id) if current_package_id else self.env["stock.quant.package"]
        product = self.env["product.product"].sudo().browse(current_product_id) if current_product_id else self.env["product.product"]
        lot = self.env["stock.lot"].sudo().browse(current_lot_id) if current_lot_id else self.env["stock.lot"]

        if not picking or not package or not product:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Please scan outgoing picking, pallet, and product first."),
                barcode=code,
                picking_id=picking_id,
                location_id=current_location_id,
                package_id=current_package_id,
                product_id=current_product_id,
                lot_id=current_lot_id,
                pending_operation=pending_operation,
                action_name="missing_quantity_context",
                success=False,
            )

        if product.tracking == "serial":
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Please scan serial number instead of entering quantity."),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                pending_operation=False,
                action_name="serial_quantity_not_allowed",
                success=False,
                next_step="scan_serial",
            )

        if product.tracking == "lot" and not lot:
            # auto_lot = self.get_single_remaining_lot(picking, package, product)
            # if auto_lot:
            #     lot = auto_lot
            #else:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Please scan lot before quantity."),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                lot_id=False,
                pending_operation=pending_operation,
                next_step="scan_lot",
                action_name="missing_lot",
                success=False,
            )

        scan_qty = self.parse_outgoing_quantity(quantity)
        if scan_qty is False:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Please input a valid positive quantity."),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                lot_id=lot.id if lot else False,
                pending_operation=pending_operation,
                action_name="invalid_quantity",
                success=False,
            )

        if picking.is_unspecified_pallet_outgoing:
            return self.process_unspecified_pallet_outgoing_quantity_scan(
                code,
                picking,
                package,
                product,
                lot,
                current_location_id,
                scan_qty,
            )

        lines = self.get_pending_outgoing_move_lines(picking, package, product, lot if lot else False)
        if not lines:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("There is no remaining demand for product %s on pallet %s.")
                % (product.display_name, package.name or package.barcode),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                lot_id=lot.id if lot else False,
                pending_operation=pending_operation,
                action_name="no_remaining_demand",
                success=False,
            )

        remaining_qty = sum(self.get_outgoing_line_remaining(line) for line in lines)
        rounding = product.uom_id.rounding
        if float_compare(scan_qty, remaining_qty, precision_rounding=rounding) > 0:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Scanned quantity %s exceeds remaining demand %s.") % (scan_qty, remaining_qty),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                lot_id=lot.id if lot else False,
                pending_operation=pending_operation,
                action_name="quantity_exceeds_demand",
                success=False,
            )

        stock_qty, stock_location = self.get_package_product_stock_qty(package, product, lot if lot else False)
        if float_compare(scan_qty, stock_qty, precision_rounding=rounding) > 0:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Scanned quantity %s exceeds pallet stock %s.") % (scan_qty, stock_qty),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                lot_id=lot.id if lot else False,
                pending_operation=pending_operation,
                action_name="quantity_exceeds_stock",
                success=False,
            )

        updated_lines = self.apply_partial_package_scan(lines, scan_qty, stock_location)

        move_line_model = self.env["stock.move.line"]
        package_lines = self.get_outgoing_package_move_lines(picking, package)
        package_done = self.are_outgoing_lines_completed(package_lines)

        picking_lines = move_line_model.sudo().search([
            ("picking_id", "=", picking.id),
            ("package_id", "!=", False),
            ("quantity", ">", 0),
        ], order="id")
        picking_done = self.are_outgoing_lines_completed(picking_lines)

        if picking_done:
            next_step = "validate"
            package_id = False
            message = _("All products scanned. Please validate outgoing picking.")
        elif package_done:
            next_step = "scan_pallet"
            package_id = False
            message = _("Pallet %s completed. Please scan next pallet.") % (package.name or package.barcode)
        else:
            next_step = "scan_product"
            package_id = package.id
            message = _("Scanned %s of %s on pallet %s.") % (
            scan_qty, product.display_name, package.name or package.barcode)

        return self.build_outgoing_scan_result(
            "quantity",
            _("Quantity"),
            message,
            barcode=code,
            picking_id=picking.id,
            location_id=current_location_id,
            package_id=package_id,
            product_id=False,
            lot_id=False,
            pending_operation=False,
            next_step=next_step,
            action_name="scan_partial_quantity",
            updated_move_line_ids=updated_lines.ids,
            success=True,
        )

    @api.model
    def process_unspecified_pallet_outgoing_serial_scan(self, code, picking, package, product, current_location_id):
        stock_data = self.get_package_stock_set(package)
        if len(stock_data["location_ids"]) != 1 or not stock_data["location"]:
            return self.build_outgoing_scan_result("error", _("Error"), _("Pallet %s must have stock in exactly one internal location.") % (package.name or package.barcode), barcode=code, picking_id=picking.id, location_id=current_location_id, package_id=package.id, product_id=product.id, action_name="serial_pallet_multiple_locations", success=False, next_step="scan_serial")
        stock_location = stock_data["location"]
        if stock_location.id != current_location_id:
            return self.build_outgoing_scan_result("error", _("Error"), _("Serial number must be scanned from location %s.") % stock_location.display_name, barcode=code, picking_id=picking.id, location_id=current_location_id, package_id=package.id, product_id=product.id, action_name="serial_location_mismatch", success=False, next_step="scan_serial")

        _moves, _remaining_by_move, remaining_qty = self.get_unspecified_pallet_outgoing_demand(picking, product)
        if float_compare(remaining_qty, 1.0, precision_rounding=product.uom_id.rounding) < 0:
            return self.build_outgoing_scan_result("error", _("Error"), _("Product %s has no remaining demand on this outgoing picking.") % product.display_name, barcode=code, picking_id=picking.id, location_id=current_location_id, package_id=package.id, product_id=product.id, action_name="serial_product_completed", success=False, next_step="scan_product")

        lot_model = self.env["stock.lot"]
        move_line_model = self.env["stock.move.line"]
        lots = lot_model.sudo().search([("name", "=", code), ("product_id", "=", product.id), ("company_id", "=", picking.company_id.id)], limit=2)
        if len(lots) > 1:
            return self.build_outgoing_scan_result("error", _("Error"), _("Serial number matched multiple records for product %s: %s") % (product.display_name, code), barcode=code, picking_id=picking.id, location_id=current_location_id, package_id=package.id, product_id=product.id, action_name="serial_multiple_matches", success=False, next_step="scan_serial")
        if not lots:
            return self.build_outgoing_scan_result("error", _("Error"), _("Serial number not found for product %s: %s") % (product.display_name, code), barcode=code, picking_id=picking.id, location_id=current_location_id, package_id=package.id, product_id=product.id, action_name="serial_not_found", success=False, next_step="scan_serial")
        lot = lots[:1]
        duplicate_line = move_line_model.sudo().search([("picking_id", "=", picking.id), ("product_id", "=", product.id), ("lot_id", "=", lot.id), ("outbound_scanned_quantity", ">", 0)], limit=1)
        if duplicate_line:
            return self.build_outgoing_scan_result("error", _("Error"), _("Serial number %s is already scanned on this outgoing picking.") % code, barcode=code, picking_id=picking.id, location_id=current_location_id, package_id=package.id, product_id=product.id, action_name="serial_duplicate_in_picking", success=False, next_step="scan_serial")

        updated_lines, error_message = self.create_unspecified_pallet_outgoing_move_lines(picking, package, stock_location, product, 1.0, lot)
        if error_message:
            return self.build_outgoing_scan_result("error", _("Error"), error_message, barcode=code, picking_id=picking.id, location_id=current_location_id, package_id=package.id, product_id=product.id, action_name="serial_not_available", success=False, next_step="scan_serial")

        if self.is_unspecified_pallet_outgoing_complete(picking):
            next_step = "validate"
            package_id = False
            product_id = False
            message = _("All products scanned. Please validate outgoing picking.")
        else:
            _moves, _remaining_by_move, remaining_qty = self.get_unspecified_pallet_outgoing_demand(picking, product)
            next_step = "scan_serial" if float_compare(remaining_qty, 0.0, precision_rounding=product.uom_id.rounding) > 0 else "scan_product"
            package_id = package.id
            product_id = product.id if next_step == "scan_serial" else False
            message = _("Serial number %s scanned. Please scan next serial number.") % code if next_step == "scan_serial" else _("Product %s completed. Please scan next product.") % product.display_name
        return self.build_outgoing_scan_result("serial", _("Serial Number"), message, barcode=code, picking_id=picking.id, location_id=current_location_id, package_id=package_id, product_id=product_id, lot_id=False, pending_operation=False, next_step=next_step, action_name="scan_unspecified_partial_serial", updated_move_line_ids=updated_lines.ids, success=True)

    @api.model
    def process_unspecified_pallet_outgoing_quantity_scan(self, code, picking, package, product, lot, current_location_id, scan_qty):
        stock_data = self.get_package_stock_set(package)
        if len(stock_data["location_ids"]) != 1 or not stock_data["location"]:
            return self.build_outgoing_scan_result("error", _("Error"), _("Pallet %s must have stock in exactly one internal location.") % (package.name or package.barcode), barcode=code, picking_id=picking.id, location_id=current_location_id, package_id=package.id, product_id=product.id, lot_id=lot.id if lot else False, action_name="quantity_pallet_multiple_locations", success=False, next_step="input_quantity")
        stock_location = stock_data["location"]
        if stock_location.id != current_location_id:
            return self.build_outgoing_scan_result("error", _("Error"), _("Product quantity must be scanned from location %s.") % stock_location.display_name, barcode=code, picking_id=picking.id, location_id=current_location_id, package_id=package.id, product_id=product.id, lot_id=lot.id if lot else False, action_name="quantity_location_mismatch", success=False, next_step="input_quantity")

        updated_lines, error_message = self.create_unspecified_pallet_outgoing_move_lines(picking, package, stock_location, product, scan_qty, lot)
        if error_message:
            return self.build_outgoing_scan_result("error", _("Error"), error_message, barcode=code, picking_id=picking.id, location_id=current_location_id, package_id=package.id, product_id=product.id, lot_id=lot.id if lot else False, action_name="quantity_not_available", success=False, next_step="input_quantity")

        if self.is_unspecified_pallet_outgoing_complete(picking):
            next_step = "validate"
            package_id = False
            message = _("All products scanned. Please validate outgoing picking.")
        else:
            next_step = "scan_product"
            package_id = package.id
            message = _("Scanned %s of %s on pallet %s.") % (scan_qty, product.display_name, package.name or package.barcode)
        return self.build_outgoing_scan_result("quantity", _("Quantity"), message, barcode=code, picking_id=picking.id, location_id=current_location_id, package_id=package_id, product_id=False, lot_id=False, pending_operation=False, next_step=next_step, action_name="scan_unspecified_partial_quantity", updated_move_line_ids=updated_lines.ids, success=True)

    @api.model
    def get_unspecified_pallet_outgoing_demand(self, picking, product):
        move_model = self.env["stock.move"]
        move_line_model = self.env["stock.move.line"]
        moves = move_model.sudo().search([("picking_id", "=", picking.id), ("product_id", "=", product.id), ("state", "!=", "cancel")], order="id")
        scanned_lines = move_line_model.sudo().search([("move_id", "in", moves.ids), ("state", "!=", "cancel"), ("is_outbound_scanned", "=", True)], order="id") if moves else move_line_model
        scanned_qty_by_move = {}
        for line in scanned_lines:
            scanned_qty_by_move[line.move_id.id] = scanned_qty_by_move.get(line.move_id.id, 0.0) + (line.outbound_scanned_quantity or 0.0)
        remaining_by_move = {}
        remaining_qty = 0.0
        for move in moves:
            remaining = max((move.product_uom_qty or 0.0) - scanned_qty_by_move.get(move.id, 0.0), 0.0)
            remaining_by_move[move.id] = remaining
            remaining_qty += remaining
        return moves, remaining_by_move, remaining_qty

    @api.model
    def get_unspecified_pallet_outgoing_suggestions(self, picking, moves, scanned_lines, demand_by_product):
        remaining_by_product = {}
        required_quantity = 0.0
        for product_id, product_data in demand_by_product.items():
            remaining_quantity = max((product_data["required_quantity"] or 0.0) - (product_data["scanned_quantity"] or 0.0), 0.0)
            remaining_by_product[product_id] = remaining_quantity
            required_quantity += remaining_quantity
        suggestion_summary = {"suggested_pallet_count": 0, "required_quantity": required_quantity, "suggested_quantity": 0.0, "shortage_quantity": required_quantity, "is_fully_covered": all(float_compare(quantity, 0.0, precision_rounding=demand_by_product[product_id]["product"].uom_id.rounding) <= 0 for product_id, quantity in remaining_by_product.items())}
        if not moves or not remaining_by_product or not picking.location_id:
            return [], suggestion_summary

        location_model = self.env["stock.location"]
        quant_model = self.env["stock.quant"]
        source_locations = location_model.sudo().search([("id", "child_of", picking.location_id.id), ("usage", "=", "internal")], order="id")
        if not source_locations:
            return [], suggestion_summary
        quants = quant_model.sudo().search([("company_id", "=", picking.company_id.id), ("location_id", "in", source_locations.ids), ("package_id", "!=", False), ("product_id", "in", list(demand_by_product)), ("quantity", ">", 0)], order="location_id, package_id, product_id, lot_id, owner_id, id")
        package_location_ids = {}
        if quants:
            package_quants = quant_model.sudo().search([("package_id", "in", quants.mapped("package_id").ids), ("location_id.usage", "=", "internal"), ("quantity", ">", 0)], order="package_id, location_id")
            for quant in package_quants:
                package_location_ids.setdefault(quant.package_id.id, set()).add(quant.location_id.id)
        scanned_qty_by_variant = {}
        for line in scanned_lines:
            product = line.product_id
            if not line.package_id or product.id not in demand_by_product:
                continue
            lot_id = line.lot_id.id if product.tracking == "lot" else 0
            key = (line.location_id.id, line.package_id.id, product.id, lot_id, line.owner_id.id or 0)
            scanned_qty_by_variant[key] = scanned_qty_by_variant.get(key, 0.0) + (line.outbound_scanned_quantity or 0.0)

        available_by_variant = {}
        for quant in quants:
            product = quant.product_id
            if len(package_location_ids.get(quant.package_id.id, set())) != 1 or (product.tracking in ("lot", "serial") and not quant.lot_id):
                continue
            available_quantity = max((quant.quantity or 0.0) - (quant.reserved_quantity or 0.0), 0.0)
            if float_compare(available_quantity, 0.0, precision_rounding=product.uom_id.rounding) <= 0:
                continue
            lot_id = quant.lot_id.id if product.tracking == "lot" else 0
            key = (quant.location_id.id, quant.package_id.id, product.id, lot_id, quant.owner_id.id or 0)
            variant = available_by_variant.setdefault(key, {"location": quant.location_id, "package": quant.package_id, "product": product, "lot": quant.lot_id if product.tracking == "lot" else self.env["stock.lot"], "owner": quant.owner_id, "available_quantity": 0.0})
            variant["available_quantity"] += available_quantity

        pallet_suggestion_by_key = {}
        suggested_quantity = 0.0
        for key in sorted(available_by_variant):
            variant = available_by_variant[key]
            product = variant["product"]
            available_quantity = max(variant["available_quantity"] - scanned_qty_by_variant.get(key, 0.0), 0.0)
            remaining_quantity = remaining_by_product.get(product.id, 0.0)
            if float_compare(available_quantity, 0.0, precision_rounding=product.uom_id.rounding) <= 0 or float_compare(remaining_quantity, 0.0, precision_rounding=product.uom_id.rounding) <= 0:
                continue
            suggested_line_quantity = min(available_quantity, remaining_quantity)
            remaining_by_product[product.id] -= suggested_line_quantity
            suggested_quantity += suggested_line_quantity
            pallet_key = (variant["location"].id, variant["package"].id)
            pallet_suggestion = pallet_suggestion_by_key.setdefault(pallet_key, {"priority": 0, "package_id": variant["package"].id, "package_name": variant["package"].name, "package_barcode": variant["package"].barcode or variant["package"].name, "source_location_id": variant["location"].id, "source_location_name": variant["location"].display_name, "suggested_total_quantity": 0.0, "products": []})
            pallet_suggestion["suggested_total_quantity"] += suggested_line_quantity
            pallet_suggestion["products"].append({"product_id": product.id, "product_name": product.display_name, "product_barcode": product.barcode or "", "default_code": product.default_code or "", "tracking": product.tracking, "lot_id": variant["lot"].id or False, "lot": variant["lot"].name or "", "owner_id": variant["owner"].id or False, "owner_name": variant["owner"].display_name or "", "available_quantity": available_quantity, "suggested_quantity": suggested_line_quantity})

        pallet_suggestions = list(pallet_suggestion_by_key.values())
        for index, pallet_suggestion in enumerate(pallet_suggestions, 1):
            pallet_suggestion["priority"] = index
        shortage_quantity = sum(max(quantity, 0.0) for quantity in remaining_by_product.values())
        suggestion_summary.update({"suggested_pallet_count": len(pallet_suggestions), "suggested_quantity": suggested_quantity, "shortage_quantity": shortage_quantity, "is_fully_covered": all(float_compare(quantity, 0.0, precision_rounding=demand_by_product[product_id]["product"].uom_id.rounding) <= 0 for product_id, quantity in remaining_by_product.items())})
        return pallet_suggestions, suggestion_summary

    @api.model
    def create_unspecified_pallet_outgoing_move_lines(self, picking, package, location, product, quantity, lot=False):
        move_line_model = self.env["stock.move.line"]
        quant_model = self.env["stock.quant"]
        moves, remaining_by_move, demand_remaining_qty = self.get_unspecified_pallet_outgoing_demand(picking, product)
        rounding = product.uom_id.rounding
        if float_compare(quantity, demand_remaining_qty, precision_rounding=rounding) > 0:
            return move_line_model, _("Scanned quantity %s exceeds remaining demand %s.") % (quantity, demand_remaining_qty)

        quant_domain = [("company_id", "=", picking.company_id.id), ("package_id", "=", package.id), ("product_id", "=", product.id), ("location_id", "=", location.id), ("quantity", ">", 0)]
        quant_domain.append(("lot_id", "=", lot.id if lot else False))
        source_quants = quant_model.sudo().search(quant_domain, order="owner_id, id")
        if not source_quants:
            return move_line_model, _("Product %s is not available on pallet %s.") % (product.display_name, package.name or package.barcode)

        scanned_domain = [("picking_id", "=", picking.id), ("package_id", "=", package.id), ("product_id", "=", product.id), ("location_id", "=", location.id), ("state", "!=", "cancel"), ("is_outbound_scanned", "=", True)]
        scanned_domain.append(("lot_id", "=", lot.id if lot else False))
        scanned_lines = move_line_model.sudo().search(scanned_domain)
        scanned_qty_by_owner = {}
        for line in scanned_lines:
            owner_id = line.owner_id.id or False
            scanned_qty_by_owner[owner_id] = scanned_qty_by_owner.get(owner_id, 0.0) + (line.outbound_scanned_quantity or 0.0)

        available_qty_by_owner = {}
        for quant in source_quants:
            owner_id = quant.owner_id.id or False
            available_qty_by_owner[owner_id] = available_qty_by_owner.get(owner_id, 0.0) + max((quant.quantity or 0.0) - (quant.reserved_quantity or 0.0), 0.0)
        available_qty = sum(max(available_qty - scanned_qty_by_owner.get(owner_id, 0.0), 0.0) for owner_id, available_qty in available_qty_by_owner.items())
        if float_compare(quantity, available_qty, precision_rounding=rounding) > 0:
            return move_line_model, _("Scanned quantity %s exceeds available pallet stock %s.") % (quantity, available_qty)

        now = fields.Datetime.now()
        remaining_qty = quantity
        created_lines = move_line_model
        for owner_id, owner_available_qty in available_qty_by_owner.items():
            owner_remaining_qty = max(owner_available_qty - scanned_qty_by_owner.get(owner_id, 0.0), 0.0)
            if float_compare(owner_remaining_qty, 0.0, precision_rounding=rounding) <= 0:
                continue
            for move in moves:
                if float_compare(remaining_qty, 0.0, precision_rounding=rounding) <= 0:
                    break
                move_remaining_qty = remaining_by_move.get(move.id, 0.0)
                if float_compare(move_remaining_qty, 0.0, precision_rounding=rounding) <= 0:
                    continue
                taken_qty = min(remaining_qty, owner_remaining_qty, move_remaining_qty)
                created_lines |= move_line_model.create({"picking_id": picking.id, "move_id": move.id, "product_id": product.id, "product_uom_id": product.uom_id.id, "quantity": taken_qty, "location_id": location.id, "location_dest_id": move.location_dest_id.id, "package_id": package.id, "result_package_id": False, "lot_id": lot.id if lot else False, "owner_id": owner_id, "is_outbound_scanned": True, "outbound_scanned_quantity": taken_qty, "outbound_scanned_by_id": self.env.user.id, "outbound_scanned_datetime": now})
                remaining_by_move[move.id] -= taken_qty
                owner_remaining_qty -= taken_qty
                remaining_qty -= taken_qty
        return created_lines, False

    @api.model
    def is_unspecified_pallet_outgoing_complete(self, picking):
        move_model = self.env["stock.move"]
        move_line_model = self.env["stock.move.line"]
        moves = move_model.sudo().search([("picking_id", "=", picking.id), ("state", "!=", "cancel")], order="id")
        if not moves:
            return False
        scanned_lines = move_line_model.sudo().search([("move_id", "in", moves.ids), ("state", "!=", "cancel"), ("is_outbound_scanned", "=", True)])
        scanned_qty_by_move = {}
        for line in scanned_lines:
            scanned_qty_by_move[line.move_id.id] = scanned_qty_by_move.get(line.move_id.id, 0.0) + (line.outbound_scanned_quantity or 0.0)
        for move in moves:
            if float_compare(scanned_qty_by_move.get(move.id, 0.0), move.product_uom_qty or 0.0, precision_rounding=move.product_uom.rounding) != 0:
                return False
        return True

    @api.model
    def normalize_outgoing_operation(self, operation):
        operation = (operation or "").strip().lower()
        return operation if operation in self.OUTGOING_OPERATIONS else False

    @api.model
    def clean_outgoing_context_for_operation(self,operation,picking_id=False,current_location_id=False,
                                             current_package_id=False,current_product_id=False,current_lot_id=False,):
        operation = self.normalize_outgoing_operation(operation)
        current = {
            "picking_id": picking_id,
            "location_id": current_location_id,
            "package_id": current_package_id,
            "product_id": current_product_id,
            "lot_id": current_lot_id,
        }
        if operation == "picking":
            return {
                "picking_id": False,
                "location_id": False,
                "package_id": False,
                "product_id": False,
                "lot_id": False,
            }
        if operation == "location":
            current.update({
                "location_id": False,
                "package_id": False,
                "product_id": False,
                "lot_id": False,
            })
        elif operation == "pallet":
            current.update({
                "package_id": False,
                "product_id": False,
                "lot_id": False,
            })
        elif operation == "product":
            current.update({
                "product_id": False,
                "lot_id": False,
            })
        elif operation == "lot":
            current.update({
                "lot_id": False,
            })
        elif operation == "serial":
            current.update({
                "lot_id": False,
            })
        return current


    @api.model
    def infer_outgoing_operation(
        self,
        picking_id=False,
        current_location_id=False,
        current_package_id=False,
        current_product_id=False,
        current_lot_id=False,
        quantity=False,):
        if not picking_id:
            return "picking"
        if not current_location_id:
            return "location"
        if not current_package_id:
            return "pallet"
        if not current_product_id:
            return "product"
        product = self.env["product.product"].sudo().browse(current_product_id)
        if product and product.tracking == "serial":
            return "serial"
        if product and product.tracking == "lot" and not current_lot_id:
            return "lot"
        if quantity not in (False, None, ""):
            return "quantity"
        return "quantity"

    @api.model
    def get_valid_outgoing_picking(self, picking_id):
        if not picking_id:
            return self.env["stock.picking"]
        return self.env["stock.picking"].sudo().search([
            ("id", "=", picking_id),
            ("picking_type_id.code", "=", "outgoing"),
            ("state", "not in", ("done", "cancel")),
        ], limit=1)

    @api.model
    def get_outgoing_picking_from_barcode(self, code):
        picking_model = self.env["stock.picking"]
        domain_base = [
            ("picking_type_id.code", "=", "outgoing"),
            ("state", "not in", ("cancel",)),
        ]
        picking = picking_model.sudo().search(domain_base + [("name", "=", code)], limit=1)
        return picking

    @api.model
    def get_outgoing_location_from_barcode(self, code):
        return self.env["stock.location"].sudo().search([
            ("barcode", "=", code),
            ("usage", "=", "internal"),
        ], limit=1)

    @api.model
    def get_outgoing_package_from_barcode(self, code):
        package_model = self.env["stock.quant.package"]
        package = package_model.sudo().search([("barcode", "=", code)], limit=1)
        return package

    @api.model
    def get_outgoing_product_from_barcode(self, code):
        product_model = self.env["product.product"]
        products = product_model.sudo().search([
            "|",
            ("barcode", "=", code),
            ("default_code", "=", code),
        ], limit=2)
        if not products:
            products = product_model.sudo().search([("name", "=", code)], limit=2)
        return products


    @api.model
    def get_outgoing_package_move_lines(self, picking, package):
        return self.env["stock.move.line"].sudo().search([
            ("picking_id", "=", picking.id),
            ("package_id", "=", package.id),
            ("quantity", ">", 0),
        ], order="id")

    @api.model
    def get_pending_outgoing_move_lines(self, picking, package, product=False, lot=False):
        domain = [
            ("picking_id", "=", picking.id),
            ("package_id", "=", package.id),
            ("quantity", ">", 0),
        ]
        if product:
            domain.append(("product_id", "=", product.id))
        if lot:
            domain.append(("lot_id", "=", lot.id))
        elif product and product.tracking == "lot":
            domain.append(("lot_id", "!=", False))
        lines = self.env["stock.move.line"].sudo().search(domain, order="id")
        return lines.filtered(lambda line: self.get_outgoing_line_remaining(line) > 0)

    @api.model
    def get_outgoing_line_remaining(self, line):
        return max((line.quantity or 0.0) - (line.outbound_scanned_quantity or 0.0), 0.0)

    @api.model
    def are_outgoing_lines_completed(self, lines):
        for line in lines:
            rounding = line.product_uom_id.rounding or line.product_id.uom_id.rounding
            if float_compare(line.outbound_scanned_quantity or 0.0, line.quantity or 0.0, precision_rounding=rounding) < 0:
                return False
        return bool(lines)

    @api.model
    def get_package_stock_set(self, package):
        quants = self.env["stock.quant"].sudo().search([
            ("package_id", "=", package.id),
            ("location_id.usage", "=", "internal"),
            ("quantity", ">", 0),
        ], order="location_id, product_id, lot_id, id")
        lines = {}
        location_ids = set()
        location = self.env["stock.location"]
        for quant in quants:
            qty = quant.quantity or 0.0
            rounding = quant.product_id.uom_id.rounding
            if float_compare(qty, 0.0, precision_rounding=rounding) <= 0:
                continue
            key = (quant.product_id.id, quant.lot_id.id if quant.lot_id else False)
            if key not in lines:
                lines[key] = {
                    "product": quant.product_id,
                    "lot": quant.lot_id,
                    "quantity": 0.0,
                    "available_quantity": 0.0,
                }
            lines[key]["quantity"] += qty
            lines[key]["available_quantity"] += max((quant.quantity or 0.0) - (quant.reserved_quantity or 0.0), 0.0)
            location_ids.add(quant.location_id.id)
            location = quant.location_id
        if len(location_ids) != 1:
            location = self.env["stock.location"]
        return {
            "lines": lines,
            "location_ids": location_ids,
            "location": location,
            "quants": quants,
        }

    @api.model
    def has_untracked_serial_stock(self, quants):
        return any(
            quant.product_id.tracking == "serial" and not quant.lot_id
            for quant in quants.filtered(lambda quant: quant.quantity > 0)
        )

    @api.model
    def get_package_demand_set(self, move_lines):
        lines = {}
        for line in move_lines:
            key = (line.product_id.id, line.lot_id.id if line.lot_id else False)
            if key not in lines:
                lines[key] = {
                    "product": line.product_id,
                    "lot": line.lot_id,
                    "quantity": 0.0,
                    "scanned_quantity": 0.0,
                }
            lines[key]["quantity"] += line.quantity or 0.0
            lines[key]["scanned_quantity"] += line.outbound_scanned_quantity or 0.0
        return lines

    @api.model
    def can_ship_whole_package(self, picking, package):
        move_lines = self.get_outgoing_package_move_lines(picking, package)
        stock_data = self.get_package_stock_set(package)
        if not move_lines:
            return False, _("No demand found for this pallet.")
        if not stock_data["lines"]:
            return False, _("No internal stock found for this pallet.")
        if len(stock_data["location_ids"]) > 1:
            return False, _("Pallet stock is split across multiple locations.")
        if self.has_untracked_serial_stock(stock_data["quants"]):
            return False, _("This pallet contains serial-tracked stock without SN.")

        stock_lines = stock_data["lines"]
        demand_lines = self.get_package_demand_set(move_lines)
        if set(stock_lines.keys()) != set(demand_lines.keys()):
            return False, _("Pallet stock does not exactly match picking demand.")
        for key, stock_line in stock_lines.items():
            product = stock_line["product"]
            demand_qty = demand_lines[key]["quantity"]
            if float_compare(stock_line["quantity"], demand_qty, precision_rounding=product.uom_id.rounding) != 0:
                return False, _("Pallet quantity does not exactly match picking demand.")
        return True, _("Pallet stock exactly matches picking demand.")

    @api.model
    def apply_whole_package_scan(self, move_lines, location):
        normal_lines = self.env["stock.move.line"].browse(move_lines.ids)
        now = fields.Datetime.now()
        for line in normal_lines:
            line.write({
                "location_id": location.id if location else line.location_id.id,
                "is_outbound_scanned": True,
                "outbound_scanned_quantity": line.quantity,
                "outbound_scanned_by_id": self.env.user.id,
                "outbound_scanned_datetime": now,
            })
        return normal_lines

    @api.model
    def apply_partial_package_scan(self, move_lines, quantity, location):
        remaining_qty = quantity
        updated_lines = self.env["stock.move.line"]
        now = fields.Datetime.now()
        for sudo_line in move_lines:
            if remaining_qty <= 0:
                break
            line = self.env["stock.move.line"].browse(sudo_line.id)
            line_remaining = self.get_outgoing_line_remaining(sudo_line)
            if line_remaining <= 0:
                continue
            take_qty = min(line_remaining, remaining_qty)
            new_scanned_qty = (sudo_line.outbound_scanned_quantity or 0.0) + take_qty
            rounding = sudo_line.product_uom_id.rounding or sudo_line.product_id.uom_id.rounding
            line.write({
                "location_id": location.id if location else sudo_line.location_id.id,
                "outbound_scanned_quantity": new_scanned_qty,
                "is_outbound_scanned": float_compare(new_scanned_qty, sudo_line.quantity or 0.0, precision_rounding=rounding) >= 0,
                "outbound_scanned_by_id": self.env.user.id,
                "outbound_scanned_datetime": now,
            })
            updated_lines |= line
            remaining_qty -= take_qty
        return updated_lines

    @api.model
    def get_single_remaining_lot(self, picking, package, product):
        lines = self.get_pending_outgoing_move_lines(picking, package, product)
        lot_ids = list(set(lines.mapped("lot_id").ids))
        if len(lot_ids) == 1:
            return self.env["stock.lot"].sudo().browse(lot_ids[0])
        return self.env["stock.lot"]

    @api.model
    def get_package_product_stock_qty(self, package, product, lot=False):
        stock_data = self.get_package_stock_set(package)
        if len(stock_data["location_ids"]) > 1:
            return 0.0, self.env["stock.location"]
        key = (product.id, lot.id if lot else False)
        stock_line = stock_data["lines"].get(key)
        if not stock_line:
            return 0.0, stock_data["location"]
        return stock_line["quantity"], stock_data["location"]

    @api.model
    def parse_outgoing_quantity(self, quantity):
        if quantity in (False, None, ""):
            return False
        try:
            qty = float(quantity)
        except (TypeError, ValueError):
            return False
        return qty if qty > 0 else False

    @api.model
    def get_outgoing_scan_state(
        self,
        picking_id=False,
        current_location_id=False,
        current_package_id=False,
        current_product_id=False,
        current_lot_id=False,
        pending_operation=False,
        last_scan=None,
    ):
        picking = self.env["stock.picking"].sudo().search([("id", "=", picking_id)], limit=1) if picking_id else self.env["stock.picking"]
        location = self.env["stock.location"].sudo().search([("id", "=", current_location_id)], limit=1) if current_location_id else self.env["stock.location"]
        package = self.env["stock.quant.package"].sudo().search([("id", "=", current_package_id)], limit=1) if current_package_id else self.env["stock.quant.package"]
        product = self.env["product.product"].sudo().search([("id", "=", current_product_id)], limit=1) if current_product_id else self.env["product.product"]
        lot = self.env["stock.lot"].sudo().search([("id", "=", current_lot_id)], limit=1) if current_lot_id else self.env["stock.lot"]

        if not picking:
            return {
                "picking": {},
                "current_location": self.format_location_for_scan_state(location),
                "current_pallet": self.format_package_for_outgoing_scan_state(package),
                "current_product": self.format_product_for_outgoing_scan_state(product),
                "current_lot": self.format_lot_for_outgoing_scan_state(lot),
                "summary": self.get_empty_outgoing_summary(),
                "pallets": [],
                "demand_products": [],
                "current_pallet_products": [],
                "pallet_suggestions": [],
                "suggestion_summary": {"suggested_pallet_count": 0, "required_quantity": 0.0, "suggested_quantity": 0.0, "shortage_quantity": 0.0, "is_fully_covered": True},
                "last_scan": last_scan or {},
            }

        is_picking_done = picking.state == "done"
        package_lines = self.env["stock.move.line"].sudo().search([
            ("picking_id", "=", picking.id),
            ("package_id", "!=", False),
            ("quantity", ">", 0),
        ], order="package_id, id")
        packages = package_lines.mapped("package_id")
        pallet_data = []
        completed_pallets = 0
        total_qty = 0.0
        scanned_qty = 0.0
        demand_products = []
        current_pallet_products = []
        pallet_suggestions = []
        suggestion_summary = {"suggested_pallet_count": 0, "required_quantity": 0.0, "suggested_quantity": 0.0, "shortage_quantity": 0.0, "is_fully_covered": True}

        if picking.is_unspecified_pallet_outgoing:
            move_model = self.env["stock.move"]
            move_line_model = self.env["stock.move.line"]
            moves = move_model.sudo().search([("picking_id", "=", picking.id), ("state", "!=", "cancel")], order="id")
            scanned_lines = move_line_model.sudo().search([("move_id", "in", moves.ids), ("state", "!=", "cancel"), ("is_outbound_scanned", "=", True)], order="id") if moves else move_line_model
            scanned_qty_by_move = {}
            pallet_scanned_qty_by_product = {}
            for line in scanned_lines:
                scanned_qty_by_move[line.move_id.id] = scanned_qty_by_move.get(line.move_id.id, 0.0) + (line.outbound_scanned_quantity or 0.0)
                if package and line.package_id == package:
                    pallet_scanned_qty_by_product[line.product_id.id] = pallet_scanned_qty_by_product.get(line.product_id.id, 0.0) + (line.outbound_scanned_quantity or 0.0)
            demand_by_product = {}
            for move in moves:
                product_data = demand_by_product.setdefault(move.product_id.id, {"product": move.product_id, "required_quantity": 0.0, "scanned_quantity": 0.0})
                product_data["required_quantity"] += move.product_uom_qty or 0.0
                product_data["scanned_quantity"] += scanned_qty_by_move.get(move.id, 0.0)
            for product_id, product_data in sorted(demand_by_product.items()):
                product = product_data["product"]
                required_quantity = product_data["required_quantity"]
                scanned_quantity = min(product_data["scanned_quantity"], required_quantity)
                demand_products.append({"product_id": product_id, "product_name": product.display_name, "product_barcode": product.barcode or "", "default_code": product.default_code or "", "tracking": product.tracking, "required_quantity": required_quantity, "scanned_quantity": scanned_quantity, "remaining_quantity": max(required_quantity - scanned_quantity, 0.0)})
            pallet_suggestions, suggestion_summary = self.get_unspecified_pallet_outgoing_suggestions(picking, moves, scanned_lines, demand_by_product)
            if package:
                pallet_stock_data = self.get_package_stock_set(package)
                pallet_available_qty_by_product = {}
                for stock_line in pallet_stock_data["lines"].values():
                    product_id = stock_line["product"].id
                    pallet_available_qty_by_product[product_id] = pallet_available_qty_by_product.get(product_id, 0.0) + stock_line["available_quantity"]
                for product_data in demand_products:
                    product = demand_by_product[product_data["product_id"]]["product"]
                    pallet_available_quantity = max(pallet_available_qty_by_product.get(product.id, 0.0) - pallet_scanned_qty_by_product.get(product.id, 0.0), 0.0)
                    if float_compare(product_data["remaining_quantity"], 0.0, precision_rounding=product.uom_id.rounding) > 0 and float_compare(pallet_available_quantity, 0.0, precision_rounding=product.uom_id.rounding) > 0:
                        current_pallet_products.append({"product_id": product.id, "product_name": product.display_name, "product_barcode": product.barcode or "", "default_code": product.default_code or "", "tracking": product.tracking, "picking_remaining_quantity": product_data["remaining_quantity"], "pallet_available_quantity": pallet_available_quantity})

        for pallet in packages:
            lines = package_lines.filtered(lambda line: line.package_id == pallet)
            stock_data = self.get_package_stock_set(pallet)
            can_whole, whole_reason = self.can_ship_whole_package(picking, pallet)
            products = []
            for line in lines:
                required_qty = line.quantity or 0.0
                line_is_complete = is_picking_done or self.is_outgoing_line_complete(line)
                line_scanned_qty = (
                    required_qty
                    if is_picking_done
                    else min(line.outbound_scanned_quantity or 0.0, required_qty)
                )
                remaining_qty = max(required_qty - line_scanned_qty, 0.0)
                total_qty += required_qty
                scanned_qty += line_scanned_qty
                products.append({
                    "move_line_id": line.id,
                    "move_id": line.move_id.id,
                    "product_id": line.product_id.id,
                    "product_name": line.product_id.display_name,
                    "product_barcode": line.product_id.barcode or "",
                    "default_code": line.product_id.default_code or "",
                    "lot_id": line.lot_id.id or False,
                    "lot": line.lot_id.name or line.lot_name or "",
                    "quantity": required_qty,
                    "scanned_quantity": line_scanned_qty,
                    "remaining_quantity": remaining_qty,
                    "uom": line.product_uom_id.name,
                    "source_location": line.location_id.display_name,
                    "dest_location": line.location_dest_id.display_name,
                    "is_complete": line_is_complete,
                })
            is_complete = is_picking_done or (
                bool(lines) and all(self.is_outgoing_line_complete(line) for line in lines)
            )
            if is_complete:
                completed_pallets += 1
            pallet_data.append({
                "package_id": pallet.id,
                "package_name": pallet.name,
                "package_barcode": pallet.barcode or pallet.name,
                "location_id": stock_data["location"].id or False,
                "location_name": stock_data["location"].display_name or "",
                "stock_location_ids": list(stock_data["location_ids"]),
                "is_complete": is_complete,
                "can_ship_whole": can_whole,
                "whole_reason": whole_reason,
                "move_line_ids": lines.ids,
                "products": products,
            })

        related_pending_picking_names = []
        if picking.outbound_order_id:
            related_picking_list = self.env["stock.picking"].sudo().search([
                ("outbound_order_id", "=", picking.outbound_order_id.id),
                ("picking_type_id.code", "=", "outgoing"),
                ("state", "!=", "cancel"),
                ("id", "!=", picking.id),
            ], order="id")
            for related_picking in related_picking_list:
                if related_picking.state == "done":
                    continue
                related_package_lines = related_picking.move_line_ids.filtered(
                    lambda line: line.package_id and line.quantity > 0 and line.state != "cancel"
                )
                if related_package_lines and not all(
                        self.is_outgoing_line_complete(line) for line in related_package_lines):
                    related_pending_picking_names.append(related_picking.name)

        if picking.is_unspecified_pallet_outgoing:
            total_qty = sum(product_data["required_quantity"] for product_data in demand_products)
            scanned_qty = sum(product_data["scanned_quantity"] for product_data in demand_products)
        total_pallets = len(packages)
        return {
            "picking": {
                "id": picking.id,
                "name": picking.name,
                "origin": picking.origin or "",
                "reference": picking.ref_1 or "",
                "partner": picking.partner_id.display_name or "",
                "state": picking.state,
                "picking_type_code": picking.picking_type_code,
                "outbound_scan_mode": picking.outbound_scan_mode or "",
            },
            "current_location": self.format_location_for_scan_state(location),
            "current_pallet": self.format_package_for_outgoing_scan_state(package),
            "current_product": self.format_product_for_outgoing_scan_state(product),
            "current_lot": self.format_lot_for_outgoing_scan_state(lot),
            "summary": {
                "total_pallets": total_pallets,
                "completed_pallets": completed_pallets,
                "pending_pallets": total_pallets - completed_pallets,
                "total_quantity": total_qty,
                "scanned_quantity": scanned_qty,
                "remaining_quantity": max(total_qty - scanned_qty, 0.0),
                "related_pending_picking_names": related_pending_picking_names,
                "related_pending_picking_count": len(related_pending_picking_names),
                "related_picking_message": (
                    _("Related outgoing picking not completed: %s") % ", ".join(related_pending_picking_names)
                    if related_pending_picking_names else ""
                ),
            },
            "pallets": pallet_data,
            "demand_products": demand_products,
            "current_pallet_products": current_pallet_products,
            "pallet_suggestions": pallet_suggestions,
            "suggestion_summary": suggestion_summary,
            "last_scan": last_scan or {},
        }

    @api.model
    def is_outgoing_line_complete(self, line):
        rounding = line.product_uom_id.rounding or line.product_id.uom_id.rounding
        return float_compare(line.outbound_scanned_quantity or 0.0, line.quantity or 0.0, precision_rounding=rounding) >= 0

    @api.model
    def get_empty_outgoing_summary(self):
        return {
            "total_pallets": 0,
            "completed_pallets": 0,
            "pending_pallets": 0,
            "total_quantity": 0.0,
            "scanned_quantity": 0.0,
            "remaining_quantity": 0.0,
        }

    @api.model
    def format_package_for_outgoing_scan_state(self, package):
        if not package:
            return {}
        return {
            "id": package.id,
            "name": package.name,
            "barcode": package.barcode or package.name,
            "display_name": package.display_name,
        }

    @api.model
    def format_product_for_outgoing_scan_state(self, product):
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
    def format_lot_for_outgoing_scan_state(self, lot):
        if not lot:
            return {}
        return {
            "id": lot.id,
            "name": lot.name,
            "product_id": lot.product_id.id,
        }

    @api.model
    def build_outgoing_scan_result(
        self,
        result_type,
        barcode_type,
        message,
        barcode="",
        picking_id=False,
        location_id=False,
        package_id=False,
        product_id=False,
        lot_id=False,
        pending_operation=False,
        action_name=False,
        updated_move_line_ids=None,
        success=True,
        next_step=False,
    ):
        pending_operation = self.normalize_outgoing_operation(pending_operation)
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
            "next_step": next_step or self.get_outgoing_next_scan_step(
                picking_id=picking_id,
                location_id=location_id,
                package_id=package_id,
                product_id=product_id,
                lot_id=lot_id,
                pending_operation=pending_operation,
            ),
            "current": {
                "picking_id": picking_id,
                "location_id": location_id,
                "package_id": package_id,
                "product_id": product_id,
                "lot_id": lot_id,
                "pending_operation": pending_operation,
            },
            "action": {
                "name": action_name or result_type,
                "updated_move_line_ids": updated_move_line_ids or [],
            },
            "scan_state": self.get_outgoing_scan_state(
                picking_id=picking_id,
                current_location_id=location_id,
                current_package_id=package_id,
                current_product_id=product_id,
                current_lot_id=lot_id,
                pending_operation=pending_operation,
                last_scan=last_scan,
            ),
        }

    @api.model
    def get_outgoing_next_scan_step(self, picking_id=False, location_id=False, package_id=False, product_id=False, lot_id=False, pending_operation=False):
        if pending_operation:
            return "input_quantity" if pending_operation == "quantity" else "scan_%s" % pending_operation
        if not picking_id:
            return "scan_picking"
        if not location_id:
            return "scan_location"
        if not package_id:
            return "scan_pallet"
        if not product_id:
            return "scan_product"
        product = self.env["product.product"].sudo().browse(product_id)
        if product and product.tracking == "serial":
            return "scan_serial"
        if product and product.tracking == "lot" and not lot_id:
            return "scan_lot"
        return "input_quantity"
