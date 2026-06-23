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
                "error",
                _("Error"),
                _("Outgoing picking %s is already done.") % picking.name,
                barcode=code,
                picking_id=picking.id,
                pending_operation=pending_operation,
                action_name="picking_already_done",
                success=False,
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
        if not move_lines:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Pallet %s is not specified on current outgoing picking.") % (package.name or package.barcode),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                pending_operation=pending_operation,
                action_name="pallet_not_in_picking",
                success=False,
            )

        if self.are_outgoing_lines_completed(move_lines):
            return self.build_outgoing_scan_result(
                "pallet",
                _("Pallet"),
                _("Pallet %s is already scanned.") % (package.name or package.barcode),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                pending_operation=False,
                action_name="pallet_already_scanned",
                success=True,
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
                package_id=package.id,
                pending_operation=pending_operation,
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
                package_id=package.id,
                pending_operation=pending_operation,
                action_name="pallet_multiple_locations",
                success=False,
            )

        can_whole, reason = self.can_ship_whole_package(picking, package)
        if can_whole:
            updated_lines = self.apply_whole_package_scan(move_lines, stock_data["location"])
            return self.build_outgoing_scan_result(
                "pallet",
                _("Pallet"),
                _("Pallet %s scanned as whole pallet.") % (package.name or package.barcode),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                pending_operation=False,
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

        lines = self.get_pending_outgoing_move_lines(picking, package, product)
        if not lines:
            return self.build_outgoing_scan_result(
                "error",
                _("Error"),
                _("Product %s has no remaining demand on pallet %s.")
                % (product.display_name, package.name or package.barcode),
                barcode=code,
                picking_id=picking.id,
                location_id=current_location_id,
                package_id=package.id,
                product_id=product.id,
                pending_operation=pending_operation,
                action_name="product_not_in_pallet_demand",
                success=False,
            )

        lot_id = False
        if product.tracking == "lot":
            lot_ids = list(set(lines.mapped("lot_id").ids))
            if len(lot_ids) == 1:
                lot_id = lot_ids[0]
                next_step = "input_quantity"
                message = _("Product %s selected. Lot was auto-selected.") % product.display_name
            else:
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
                pending_operation=pending_operation,
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
                pending_operation=pending_operation,
                action_name="lot_not_found",
                success=False,
            )

        lines = self.get_pending_outgoing_move_lines(picking, package, product, lot)
        if not lines:
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
                lot_id=lot.id,
                pending_operation=pending_operation,
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

        if product.tracking == "lot" and not lot:
            auto_lot = self.get_single_remaining_lot(picking, package, product)
            if auto_lot:
                lot = auto_lot
            else:
                return self.build_outgoing_scan_result(
                    "error",
                    _("Error"),
                    _("Please scan lot before quantity."),
                    barcode=code,
                    picking_id=picking.id,
                    location_id=current_location_id,
                    package_id=package.id,
                    product_id=product.id,
                    pending_operation=pending_operation,
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
        package_lines = self.get_outgoing_package_move_lines(picking, package)
        package_done = self.are_outgoing_lines_completed(package_lines)

        return self.build_outgoing_scan_result(
            "quantity",
            _("Quantity"),
            _("Scanned %s of %s on pallet %s.") % (scan_qty, product.display_name, package.name or package.barcode),
            barcode=code,
            picking_id=picking.id,
            location_id=current_location_id,
            package_id=False if package_done else package.id,
            product_id=False,
            lot_id=False,
            pending_operation=False,
            next_step="scan_pallet" if package_done else "scan_product",
            action_name="scan_partial_quantity",
            updated_move_line_ids=updated_lines.ids,
            success=True,
        )

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
            ("state", "not in", ("cancel")),
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
                "last_scan": last_scan or {},
            }

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

        for pallet in packages:
            lines = package_lines.filtered(lambda line: line.package_id == pallet)
            stock_data = self.get_package_stock_set(pallet)
            can_whole, whole_reason = self.can_ship_whole_package(picking, pallet)
            products = []
            for line in lines:
                required_qty = line.quantity or 0.0
                line_scanned_qty = min(line.outbound_scanned_quantity or 0.0, required_qty)
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
                    "scanned_quantity": line.outbound_scanned_quantity or 0.0,
                    "remaining_quantity": remaining_qty,
                    "uom": line.product_uom_id.name,
                    "source_location": line.location_id.display_name,
                    "dest_location": line.location_dest_id.display_name,
                    "is_complete": self.is_outgoing_line_complete(line),
                })
            is_complete = bool(lines) and all(self.is_outgoing_line_complete(line) for line in lines)
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
                related_package_lines = related_picking.move_line_ids.filtered(
                    lambda line: line.package_id and line.quantity > 0 and line.state != "cancel"
                )
                if related_package_lines and not all(
                        self.is_outgoing_line_complete(line) for line in related_package_lines):
                    related_pending_picking_names.append(related_picking.name)

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
        if product and product.tracking == "lot" and not lot_id:
            return "scan_lot"
        return "input_quantity"
