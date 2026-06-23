# -*- coding: utf-8 -*-

from odoo import _, fields, models,api


class StockBarcodeLiteScanService(models.AbstractModel):
    _name = "stock.barcode.lite.scan.service"
    _description = "Stock Barcode Lite Scan Service"

    @api.model
    def process_incoming_scan_barcode(self, code, picking_id=False, current_location_id=False):

        code = (code or "").strip()
        if not code:
            return self.build_scan_result(
                "error",
                _("Error"),
                _("Please scan a barcode."),
                barcode=code,
                picking_id=picking_id,
                location_id=current_location_id,
                action_name="scan_error",
                success=False,
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
                    "error",
                    _("Error"),
                    _("Incoming picking %s is already done.") % picking.name,
                    barcode=code,
                    picking_id=picking.id,
                    location_id=current_location_id,
                    action_name="picking_already_done",
                    success=False,
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
        return self.build_scan_result(
            "package",
            _("Pallet"),
            _("Pallet %s updated to %s. Move lines: %s") % (package.name, location.display_name, updated_count),
            barcode=code,
            picking_id=picking.id,
            location_id=location.id,
            package_id=package.id,
            action_name="update_package_location",
            updated_move_line_ids=move_lines.ids,
            success=True,
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
        if not package:
            package = package_model.sudo().search([("name", "=", code)], limit=1)
        return package

    @api.model
    def get_package_move_lines(self, picking, package):

        return self.env["stock.move.line"].sudo().search([
            ("picking_id", "=", picking.id),
            ("result_package_id", "=", package.id),
        ])

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
    def get_incoming_scan_state(self, picking_id=False, current_location_id=False, last_scan=None):
        picking = self.env["stock.picking"].sudo().search([("id", "=", picking_id)], limit=1) if picking_id else self.env["stock.picking"]
        location = self.env["stock.location"].sudo().search([("id", "=", current_location_id)], limit=1) if current_location_id else self.env["stock.location"]
        if not picking:
            return {
                "picking": {},
                "current_location": self.format_location_for_scan_state(location),
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

        package_lines = picking.move_line_ids.filtered(lambda line: line.result_package_id)
        packages = package_lines.mapped("result_package_id")
        pallet_data = []
        updated_pallets = 0
        for package in packages:
            lines = package_lines.filtered(lambda line: line.result_package_id == package)
            is_location_updated = bool(lines) and all(lines.mapped("is_location_updated"))
            if is_location_updated:
                updated_pallets += 1
            pallet_location = lines[:1].location_dest_id if lines else self.env["stock.location"]
            products = []
            for line in lines:
                products.append({
                    "move_line_id": line.id,
                    "move_id": line.move_id.id,
                    "product_id": line.product_id.id,
                    "product_name": line.product_id.display_name,
                    "product_barcode": line.product_id.barcode or "",
                    "default_code": line.product_id.default_code or "",
                    "quantity": line.quantity,
                    "qty_done": line.quantity,
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
        updated_move_lines = len(package_lines.filtered(lambda line: line.is_location_updated))
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
    def build_scan_result(self, result_type, barcode_type, message, barcode="",
                          picking_id=False, location_id=False, package_id=False,
                          action_name=False, updated_move_line_ids=None, success=True):

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
            "next_step": self.get_next_scan_step(result_type, picking_id, location_id),
            "current": {
                "picking_id": picking_id,
                "location_id": location_id,
                "package_id": package_id,
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
