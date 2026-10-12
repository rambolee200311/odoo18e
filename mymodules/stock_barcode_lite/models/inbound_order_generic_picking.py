# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class InboundOrder(models.Model):
    _inherit = "world.depot.inbound.order"

    def action_create_stock_picking(self):
        picking_model = self.env["stock.picking"]
        move_model = self.env["stock.move"]
        move_line_model = self.env["stock.move.line"]
        package_model = self.env["stock.quant.package"]
        lot_model = self.env["stock.lot"]
        created_picking_count = 0
        created_package_count = 0

        for record in self:
            if record.project.name == "SUNRISE":
                raise UserError(_("SUNRISE inbound orders must use Sunrise Create Receipt."))
            if record.state != "confirm":
                raise UserError(_("Stock picking can only be created from confirmed orders."))
            if not record.reference:
                raise UserError(_("Reference must be set before creating a stock picking."))
            if not record.project:
                raise UserError(_("Project is required to create a stock picking."))
            if not record.pick_type or record.pick_type.code != "incoming":
                raise UserError(_("An incoming picking type is required to create a receipt."))
            if not record.pick_type.default_location_src_id or not record.pick_type.default_location_dest_id:
                raise UserError(_("The incoming picking type must have both source and destination locations."))

            generation_mode = record.project.package_generation_mode or "picking"
            scan_mode = record.project.barcode_scan_mode or "native"
            if generation_mode not in ("inbound", "picking", "none"):
                raise UserError(_("Invalid Package Generation Mode."))
            if generation_mode == "none" and scan_mode == "custom":
                raise UserError(_("Custom Barcode Lite inbound scanning requires Package Generation Mode to create packages."))
            existing_picking = picking_model.sudo().search([
                ("inbound_order_id", "=", record.id), ("state", "!=", "cancel"),
            ], limit=1)
            if existing_picking:
                raise UserError(_("A stock picking already exists for this Inbound Order."))
            if not record.inbound_order_product_ids:
                raise UserError(_("At least one pallet line is required to create a receipt."))

            product_move_data = {}
            for pallet_line in record.inbound_order_product_ids:
                pallet_count = int(pallet_line.pallets)
                if pallet_count <= 0 or float_compare(pallet_line.pallets, pallet_count, precision_rounding=0.000001):
                    raise UserError(_("Pallet quantity on line %s must be a positive integer.") % pallet_line.display_name)
                if not pallet_line.inbound_order_product_pallet_ids:
                    raise UserError(_("Pallet line %s has no product details.") % pallet_line.display_name)
                if generation_mode == "none" and pallet_line.package_id:
                    raise UserError(_("Pallet line %s has a package although Package Generation Mode is No Package.") % pallet_line.display_name)
                if generation_mode == "inbound":
                    if pallet_count != 1:
                        raise UserError(_("Inbound-generated packages require one physical pallet per line. Split pallet line %s first.") % pallet_line.display_name)
                    if not pallet_line.package_id or not pallet_line.package_id.barcode:
                        raise UserError(_("Pallet line %s has no system package barcode. Generate the package before creating the receipt.") % pallet_line.display_name)
                for detail_line in pallet_line.inbound_order_product_pallet_ids:
                    if not detail_line.product_id or detail_line.quantity <= 0:
                        raise UserError(_("Every pallet product detail must have a product and a positive quantity."))
                    product_data = product_move_data.setdefault(detail_line.product_id.id, {
                        "product": detail_line.product_id, "quantity": 0.0,
                    })
                    product_data["quantity"] += detail_line.quantity * pallet_count

            picking = picking_model.create({
                "picking_type_id": record.pick_type.id,
                "location_id": record.pick_type.default_location_src_id.id,
                "location_dest_id": record.pick_type.default_location_dest_id.id,
                "origin": record.billno,
                "partner_id": record.owner.id,
                "owner_id": record.owner.id,
                "inbound_order_id": record.id,
                "bill_of_lading": record.bl_no,
                "cntrno": record.cntr_no,
                "ref_1": record.reference,
                "planning_date": record.a_date,
                "project_id": record.project.id,
            })
            product_moves = {}
            for product_id, product_data in product_move_data.items():
                product = product_data["product"]
                product_moves[product_id] = move_model.create({
                    "name": product.display_name,
                    "product_id": product.id,
                    "product_uom_qty": product_data["quantity"],
                    "product_uom": product.uom_id.id,
                    "picking_id": picking.id,
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                    "description_picking": _("Inbound receipt for %s") % product.display_name,
                })

            for pallet_line in record.inbound_order_product_ids:
                pallet_count = int(pallet_line.pallets)
                for pallet_index in range(1, pallet_count + 1):
                    package = False
                    if generation_mode == "inbound":
                        package = pallet_line.package_id
                    elif generation_mode == "picking":
                        package_name = pallet_line.pallet_no or "%s-%s" % (record.reference, pallet_line.id)
                        if pallet_count > 1:
                            package_name = "%s-%03d" % (package_name, pallet_index)
                        package = package_model.create({
                            "name": package_name,
                            "package_use": "disposable",
                            "billno": record.billno,
                            "reference": record.reference,
                            "cntr_no": record.cntr_no,
                            "inbound_order_id": record.id,
                            "original_pallet_no": pallet_line.pallet_no,
                        })
                        if not package.barcode:
                            raise UserError(_("Could not generate a system barcode for pallet %s.") % package.display_name)
                        created_package_count += 1

                    for detail_line in pallet_line.inbound_order_product_pallet_ids:
                        product = detail_line.product_id
                        move = product_moves[product.id]
                        lot = False
                        if product.tracking == "lot":
                            lot_name = detail_line.lot_name or "%s-%s-%s-%03d" % (
                                record.reference, record.cntr_no or "NO-CONTAINER", pallet_line.id, pallet_index,
                            )
                            lot = lot_model.sudo().search([
                                ("name", "=", lot_name), ("product_id", "=", product.id),
                                ("company_id", "=", picking.company_id.id),
                            ], limit=1)
                            if not lot:
                                lot = lot_model.create({
                                    "name": lot_name, "product_id": product.id, "company_id": picking.company_id.id,
                                })
                        move_line_values = {
                            "picking_id": picking.id,
                            "move_id": move.id,
                            "product_id": product.id,
                            "product_uom_id": product.uom_id.id,
                            "location_id": picking.location_id.id,
                            "location_dest_id": picking.location_dest_id.id,
                            "result_package_id": package.id if package else False,
                            "lot_id": lot.id if lot else False,
                            "lot_name": lot.name if lot else False,
                            "inbound_order_product_pallet_id": detail_line.id,
                        }
                        if product.tracking == "serial":
                            serial_quantity = int(detail_line.quantity)
                            if serial_quantity <= 0 or float_compare(detail_line.quantity, serial_quantity, precision_rounding=product.uom_id.rounding):
                                raise UserError(_("Serial-tracked product %s must have a positive integer quantity per pallet.") % product.display_name)
                            for serial_index in range(serial_quantity):
                                move_line_model.create(dict(move_line_values, quantity=1.0))
                        else:
                            move_line_model.create(dict(move_line_values, quantity=detail_line.quantity))
            record.write({"stock_picking_id": picking.id})
            created_picking_count += 1

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Stock Picking Created"),
                "message": _("Created %s receipt(s) and %s pallet package(s).") % (created_picking_count, created_package_count),
                "sticky": False,
            },
        }

    def action_print_system_pallet_labels(self):
        package_model = self.env["stock.quant.package"]
        package_ids = package_model
        for record in self:
            package_ids |= package_model.sudo().search([
                ("inbound_order_id", "=", record.id),
            ], order="id asc")
        if not package_ids:
            raise UserError(_("No system pallet packages were found for the selected inbound order."))
        return self.env.ref("stock_barcode_lite.action_report_system_pallet_label").report_action(package_ids)
