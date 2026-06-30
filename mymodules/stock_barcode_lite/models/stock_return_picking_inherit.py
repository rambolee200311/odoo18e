from odoo import models
from odoo.tools.float_utils import float_compare, float_is_zero
from odoo import _, models
from odoo.exceptions import UserError

class StockReturnPickingInherit(models.TransientModel):
    _inherit = "stock.return.picking"

    def action_create_returns(self):
        res = super().action_create_returns()
        for rec in self:
            picking_id = rec.get_return_picking_id_from_action(res)
            if not picking_id:
                continue

            return_picking = rec.env["stock.picking"].sudo().browse(picking_id)
            if not return_picking.exists():
                continue

            if not rec.is_sunrise_return_picking(return_picking):
                continue

            rec.apply_original_package_to_return_picking(return_picking)

        return res

    def get_return_picking_id_from_action(self, action):
        if not isinstance(action, dict):
            return False
        return action.get("res_id")

    def is_sunrise_return_picking(self, return_picking):
        original_picking = return_picking.move_ids_without_package.mapped("origin_returned_move_id.picking_id")[:1]
        if not original_picking:
            original_picking = return_picking.return_id

        if not original_picking:
            return False

        if "outbound_order_id" not in original_picking._fields:
            return False

        outbound_order = original_picking.outbound_order_id
        if not outbound_order or not outbound_order.project:
            return False

        return outbound_order.project.name == "SUNRISE"

    def apply_original_package_to_return_picking(self, return_picking):
        for return_move in return_picking.move_ids_without_package:
            original_move = return_move.origin_returned_move_id
            if not original_move:
                continue

            allocations = self.get_original_package_allocations(return_move, original_move)
            if not allocations:
                continue

            self.sync_return_move_lines_to_packages(return_move, allocations)

    def get_original_package_allocations(self, return_move, original_move):
        rounding = return_move.product_uom.rounding or return_move.product_id.uom_id.rounding
        remaining_qty = return_move.product_uom_qty
        allocations = []
        package_location_map = {}

        original_lines = original_move.move_line_ids.filtered(
            lambda line: line.product_id == return_move.product_id
            and line.package_id
            and not float_is_zero(line.quantity, precision_rounding=rounding)
        )

        for original_line in original_lines:
            if float_is_zero(remaining_qty, precision_rounding=rounding):
                break

            qty = min(remaining_qty, original_line.quantity)
            if float_is_zero(qty, precision_rounding=rounding):
                continue
            package = original_line.package_id
            if package.id not in package_location_map:
                package_quant_list = self.env["stock.quant"].sudo().search([
                    ("package_id", "=", original_line.package_id.id),
                    ("location_id.usage", "=", "internal"),
                    ("quantity", ">", 0),
                ])
                package_location_list = package_quant_list.mapped("location_id")

                if len(package_location_list) > 1:
                    raise UserError(_("Pallet %s has stock in multiple locations.") % original_line.package_id.name)

                package_location_map[package.id] = package_location_list[:1].id or original_line.location_id.id

            allocations.append({
                "package_id": original_line.package_id.id,
                "lot_id": original_line.lot_id.id if original_line.lot_id else False,
                "owner_id": original_line.owner_id.id if original_line.owner_id else False,
                "quantity": qty,
                "location_dest_id": package_location_map[package.id],
            })
            remaining_qty -= qty
        if not float_is_zero(remaining_qty, precision_rounding=rounding):
            raise UserError(
                _("Return quantity %s for product %s is greater than original package move lines.")
                % (return_move.product_uom_qty, return_move.product_id.display_name)
            )
        return allocations


    def sync_return_move_lines_to_packages(self, return_move, allocations):
        move_line_model = self.env["stock.move.line"]
        return_lines = return_move.move_line_ids.sorted("id")

        for index, allocation in enumerate(allocations):
            vals = self.get_return_move_line_package_vals(return_move, allocation)

            if index < len(return_lines):
                move_line = move_line_model.browse(return_lines[index].id)
                move_line.write(vals)
            else:
                move_line_model.create(vals)

        extra_lines = return_lines[len(allocations):]
        if extra_lines:
            move_line_model.browse(extra_lines.ids).unlink()

    def get_return_move_line_package_vals(self, return_move, allocation):
        return {
            "picking_id": return_move.picking_id.id,
            "move_id": return_move.id,
            "product_id": return_move.product_id.id,
            "product_uom_id": return_move.product_uom.id,
            "location_id": return_move.location_id.id,
            "location_dest_id": allocation["location_dest_id"],
            "lot_id": allocation["lot_id"],
            "owner_id": allocation["owner_id"],
            "quantity": allocation["quantity"],
            "result_package_id": allocation["package_id"],
        }