# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


class AutomaticPalletOutboundPicking(models.Model):
    _inherit = "world.depot.outbound.order"

    def action_create_automatic_pallet_outgoing_picking(self):
        for rec in self:
            if rec.barcode_scan_mode != "custom":
                raise UserError(_("This picking can only be created for custom barcode scanning."))
        picking_model = self.env["stock.picking"]
        group_model = self.env["procurement.group"]
        move_model = self.env["stock.move"]
        quant_model = self.env["stock.quant"]

        for rec in self:
            rec.check_custom_barcode_outgoing_one_step()
            if rec.project.pallet_structure_mode != "unknown":
                raise UserError(_("Automatic pallet picking is only available for Unknown Pallet Structure."))
            if rec.project.package_generation_mode != "inbound":
                raise UserError(_("Automatic pallet picking requires Package Generation Mode to be Inbound."))
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

            available_by_quant = {}
            for quant in source_quants:
                available_by_quant[quant.id] = max(quant.quantity - quant.reserved_quantity, 0.0)

            partial_pallet_plan = []

            for quant in source_quants:
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
                    partial_pallet_plan.append({"line": line, "quantity": allocated_quantity})
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

            partial_picking = picking_model.create({
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
                "outbound_scan_mode": "partial_pallet",
                "is_unspecified_pallet_outgoing": True,
                "project_id": rec.project.id,
            })
            quantity_by_line = {}
            for allocation in partial_pallet_plan:
                line = allocation["line"]
                quantity_by_line[line.id] = quantity_by_line.get(line.id, 0.0) + allocation["quantity"]

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
                    "picking_id": partial_picking.id,
                    "location_id": source_location.id,
                    "location_dest_id": destination_location.id,
                    "outbound_order_product_id": line.id,
                    "group_id": group.id,
                })
                created_moves |= move

            created_moves._action_confirm(merge=False)
            automatic_move_lines = created_moves.move_line_ids
            if automatic_move_lines:
                automatic_move_lines.unlink()
            created_moves._recompute_state()

            rec.write({
                "whole_pallet_picking_id": False,
                "partial_pallet_picking_id": partial_picking.id,
                "picking_PICK": partial_picking.id,
                "picking_Out": partial_picking.id,
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
