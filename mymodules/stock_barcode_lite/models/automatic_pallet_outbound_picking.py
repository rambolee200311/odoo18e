# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


class AutomaticPalletOutboundPicking(models.Model):
    _inherit = "world.depot.outbound.order"

    def action_create_automatic_pallet_outgoing_picking(self):
        picking_model = self.env["stock.picking"]
        group_model = self.env["procurement.group"]
        move_model = self.env["stock.move"]
        quant_model = self.env["stock.quant"]

        for rec in self:
            rec.check_custom_barcode_outgoing_one_step()
            if rec.project.package_generation_mode != "picking":
                raise UserError(_("Automatic pallet picking requires Package Generation Mode to be Picking."))
            if rec.state != "confirm":
                raise UserError(_("Only confirmed outbound orders can create a picking."))
            if not rec.pick_type or rec.pick_type.code != "outgoing":
                raise UserError(_("Please select an outgoing picking type."))
            if not rec.pick_type.warehouse_id:
                raise UserError(_("The outgoing picking type must belong to a warehouse."))
            if rec.warehouse and rec.warehouse != rec.pick_type.warehouse_id:
                raise UserError(_("The outbound order warehouse must match the outgoing picking type warehouse."))
            if not rec.outbound_order_product_ids:
                raise UserError(_("Please add outbound product lines."))

            existing_picking = picking_model.sudo().search([
                ("outbound_order_id", "=", rec.id),
                ("picking_type_id.code", "=", "outgoing"),
                ("return_id", "=", False),
                ("state", "!=", "cancel"),
            ], limit=1)
            if existing_picking:
                raise UserError(_("A stock picking already exists for this outbound order."))

            source_location = rec.pick_type.default_location_src_id
            destination_location = rec.pick_type.default_location_dest_id
            warehouse = rec.pick_type.warehouse_id
            company = rec.pick_type.company_id or self.env.company
            if not source_location or not destination_location:
                raise UserError(_("The outgoing picking type must define source and destination locations."))

            remaining_by_line = {}
            lines_by_product = {}
            product_ids = []
            for line in rec.outbound_order_product_ids:
                if not line.product_id:
                    raise UserError(_("Product is required on every outbound product line."))
                if float_compare(line.quantity, 0.0, precision_rounding=line.product_id.uom_id.rounding) <= 0:
                    raise UserError(_("Quantity must be greater than zero for product %s.") % line.product_id.display_name)
                if line.product_id.tracking == "serial" and not rec.pick_type.use_existing_lots:
                    raise UserError(_("The outgoing picking type must enable Use Existing Lots/Serial Numbers for product %s.") % line.product_id.display_name)
                remaining_by_line[line.id] = line.quantity
                lines_by_product.setdefault(line.product_id.id, []).append(line)
                product_ids.append(line.product_id.id)

            source_quants = quant_model.sudo().search([
                ("company_id", "=", company.id),
                ("product_id", "in", product_ids),
                ("package_id", "!=", False),
                ("quantity", ">", 0),

                ("location_id", "child_of", warehouse.view_location_id.id),
                ("location_id.usage", "=", "internal"),
            ], order="in_date asc, id asc")
            if not source_quants:
                raise UserError(_("No available pallet stock was found in the configured source location."))

            package_ids = source_quants.mapped("package_id").ids
            package_quants = quant_model.sudo().search([
                ("company_id", "=", company.id),
                ("package_id", "in", package_ids),
                ("quantity", ">", 0),
                ("location_id.usage", "=", "internal"),
            ], order="product_id, lot_id, in_date asc, id asc")
            package_quants_by_id = {}
            for quant in package_quants:
                package_quants_by_id.setdefault(quant.package_id.id, []).append(quant)

            for package_id, quant_list in package_quants_by_id.items():
                location_ids = {quant.location_id.id for quant in quant_list}
                if len(location_ids) > 1:
                    package = quant_list[0].package_id
                    raise UserError(_("Pallet %s has stock in multiple internal locations.") % (package.name or package.barcode))

            available_by_quant = {}
            for quant in source_quants:
                available_by_quant[quant.id] = max(quant.quantity - quant.reserved_quantity, 0.0)

            whole_pallet_plan = []
            partial_pallet_plan = []
            whole_package_ids = set()
            package_data = []
            for package_id, quant_list in package_quants_by_id.items():
                package_data.append((min(quant.in_date or fields.Datetime.now() for quant in quant_list), package_id, quant_list))

            for _in_date, package_id, quant_list in sorted(package_data, key=lambda data: (data[0], data[1])):
                temporary_remaining = dict(remaining_by_line)
                temporary_plan = []
                is_whole_pallet = True
                for quant in quant_list:
                    product = quant.product_id
                    rounding = product.uom_id.rounding
                    if not float_is_zero(quant.reserved_quantity, precision_rounding=rounding) or (product.tracking == "serial" and not quant.lot_id):
                        is_whole_pallet = False
                        break
                    quantity_to_allocate = quant.quantity
                    for line in lines_by_product.get(product.id, []):
                        remaining_quantity = temporary_remaining[line.id]
                        if float_compare(remaining_quantity, 0.0, precision_rounding=rounding) <= 0:
                            continue
                        allocated_quantity = min(quantity_to_allocate, remaining_quantity)
                        temporary_plan.append({"line": line, "quant": quant, "quantity": allocated_quantity})
                        temporary_remaining[line.id] -= allocated_quantity
                        quantity_to_allocate -= allocated_quantity
                        if float_is_zero(quantity_to_allocate, precision_rounding=rounding):
                            break
                    if not float_is_zero(quantity_to_allocate, precision_rounding=rounding):
                        is_whole_pallet = False
                        break
                if not is_whole_pallet:
                    continue
                package = quant_list[0].package_id
                if not package.barcode:
                    raise UserError(_("Pallet %s has no system barcode. Generate and print its system label before creating the outbound picking.") % package.name)
                remaining_by_line = temporary_remaining
                whole_pallet_plan.extend(temporary_plan)
                whole_package_ids.add(package_id)
                for quant in quant_list:
                    available_by_quant[quant.id] = 0.0

            for quant in source_quants:
                if quant.package_id.id in whole_package_ids:
                    continue
                product = quant.product_id
                rounding = product.uom_id.rounding
                available_quantity = available_by_quant[quant.id]
                if float_compare(available_quantity, 0.0, precision_rounding=rounding) <= 0:
                    continue
                for line in lines_by_product.get(product.id, []):
                    remaining_quantity = remaining_by_line[line.id]
                    if float_compare(remaining_quantity, 0.0, precision_rounding=rounding) <= 0:
                        continue
                    if not quant.package_id.barcode:
                        raise UserError(_("Pallet %s has no system barcode. Generate and print its system label before creating the outbound picking.") % quant.package_id.name)
                    allocated_quantity = min(available_quantity, remaining_quantity)
                    partial_pallet_plan.append({"line": line, "quant": quant, "quantity": allocated_quantity})
                    remaining_by_line[line.id] -= allocated_quantity
                    available_quantity -= allocated_quantity
                    if float_is_zero(available_quantity, precision_rounding=rounding):
                        break

            missing_lines = []
            for line in rec.outbound_order_product_ids:
                rounding = line.product_id.uom_id.rounding
                if float_compare(remaining_by_line[line.id], 0.0, precision_rounding=rounding) > 0:
                    missing_lines.append("%s (%s)" % (line.product_id.display_name, remaining_by_line[line.id]))
            if missing_lines:
                raise UserError(_("Insufficient available pallet stock: %s") % "; ".join(missing_lines))

            group = group_model.sudo().search([("name", "=", rec.billno)], limit=1)
            if not group:
                group = group_model.create({"name": rec.billno})

            picking_by_mode = {}
            for scan_mode, allocation_plan in (("whole_pallet", whole_pallet_plan), ("partial_pallet", partial_pallet_plan)):
                if not allocation_plan:
                    continue
                picking = picking_model.create({
                    "picking_type_id": rec.pick_type.id,
                    "location_id": source_location.id,
                    "location_dest_id": destination_location.id,
                    "origin": rec.billno,
                    "partner_id": rec.unload_company.id,
                    "outbound_order_id": rec.id,
                    "scheduled_date": rec.p_date,
                    "planning_date": rec.p_date,
                    "ref_1": rec.reference,
                    "load_ref": rec.load_ref,
                    "group_id": group.id,
                    "owner_id": rec.owner.id if rec.owner else False,
                    "outbound_scan_mode": scan_mode,
                    "is_unspecified_pallet_outgoing": scan_mode == "partial_pallet",
                    "project_id": rec.project.id,
                })
                picking_by_mode[scan_mode] = picking
                quantity_by_line = {}
                for allocation in allocation_plan:
                    line = allocation["line"]
                    quantity_by_line[line.id] = quantity_by_line.get(line.id, 0.0) + allocation["quantity"]

                moves_by_line = {}
                created_moves = move_model
                for line in rec.outbound_order_product_ids:
                    quantity = quantity_by_line.get(line.id, 0.0)
                    if float_is_zero(quantity, precision_rounding=line.product_id.uom_id.rounding):
                        continue
                    move = move_model.create({
                        "name": line.product_id.display_name,
                        "product_id": line.product_id.id,
                        "product_uom_qty": quantity,
                        "product_uom": line.product_id.uom_id.id,
                        "picking_id": picking.id,
                        "location_id": source_location.id,
                        "location_dest_id": destination_location.id,
                        "outbound_order_product_id": line.id,
                        "group_id": group.id,
                    })
                    created_moves |= move
                    moves_by_line[line.id] = move

                created_moves._action_confirm(merge=False)
                automatic_move_lines = created_moves.move_line_ids
                if automatic_move_lines:
                    automatic_move_lines.unlink()

                if scan_mode == "partial_pallet":
                    created_moves._recompute_state()
                    continue

                for allocation in allocation_plan:
                    line = allocation["line"]
                    quant = allocation["quant"]
                    move = moves_by_line[line.id]
                    taken_quantity = move._update_reserved_quantity(
                        allocation["quantity"],
                        quant.location_id,
                        lot_id=quant.lot_id,
                        package_id=quant.package_id,
                        owner_id=quant.owner_id,
                        strict=True,
                    )
                    if float_compare(taken_quantity, allocation["quantity"], precision_rounding=line.product_id.uom_id.rounding) != 0:
                        raise UserError(_("Stock changed while reserving pallet %s. Please retry.") % (quant.package_id.name or quant.package_id.barcode))
                created_moves._recompute_state()

            whole_picking = picking_by_mode.get("whole_pallet")
            partial_picking = picking_by_mode.get("partial_pallet")
            first_picking = whole_picking or partial_picking
            rec.write({
                "whole_pallet_picking_id": whole_picking.id if whole_picking else False,
                "partial_pallet_picking_id": partial_picking.id if partial_picking else False,
                "picking_PICK": whole_picking.id if whole_picking else first_picking.id,
                "picking_Out": partial_picking.id if partial_picking else first_picking.id,
                "status": "outbound",
            })

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Automatic pallet outbound picking created successfully."),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "reload"}
            },
        }
