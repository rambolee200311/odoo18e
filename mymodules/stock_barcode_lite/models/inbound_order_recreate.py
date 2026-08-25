from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class InboundOrderRecreate(models.Model):
    _inherit = "world.depot.inbound.order"

    def action_sunrise_prepare_recreate_incoming_picking(self):
        picking_model = self.env["stock.picking"]
        return_wizard_model = self.env["stock.return.picking"]

        for rec in self:
            if not self.env.user.has_group(
                "stock_barcode_lite.group_sunrise_stock_manager"
            ):
                raise UserError(
                    _("Only Sunrise stock managers can recreate receipts.")
                )
            if rec.project.name != "SUNRISE":
                raise UserError(
                    _("Only SUNRISE inbound orders can recreate receipts.")
                )
            if rec.state != "confirm":
                raise UserError(
                    _("Only confirmed inbound orders can recreate receipts.")
                )

            original_picking_list = rec.stock_picking_id.filtered(
                lambda picking: picking.state != "cancel"
            )
            original_picking_list = rec.get_sunrise_inbound_picking_backorder_chain(
                original_picking_list
            )
            if not original_picking_list:
                raise UserError(
                    _("No inbound picking was found for order %s.") % rec.reference
                )

            return_picking_list = picking_model.sudo().search([
                ("return_id", "in", original_picking_list.ids),
            ])
            return_picking_list = rec.get_sunrise_inbound_picking_backorder_chain(
                return_picking_list
            )
            pending_return_picking = return_picking_list.filtered(
                lambda picking: picking.state not in ("done", "cancel")
            )[:1]
            if pending_return_picking:
                raise UserError(
                    _(
                        "Receipt %s has an unfinished return picking or return "
                        "backorder %s. Please finish or cancel it first."
                    )
                    % (
                        pending_return_picking.return_id.name
                        or pending_return_picking.backorder_id.name,
                        pending_return_picking.name,
                    )
                )

            original_picking_names = ", ".join(original_picking_list.mapped("name"))
            done_picking_list = original_picking_list.filtered(
                lambda picking: picking.state == "done"
            )
            not_done_picking_list = original_picking_list.filtered(
                lambda picking: picking.state not in ("done", "cancel")
            )
            rec.validate_sunrise_inbound_auto_return_allowed(original_picking_list)
            for picking in not_done_picking_list:
                picking.unlink()

            for picking in done_picking_list:
                if rec.picking_has_full_done_return(picking):
                    continue

                return_wizard = return_wizard_model.with_context(
                    active_model="stock.picking",
                    active_id=picking.id,
                    active_ids=picking.ids,
                ).create({
                    "picking_id": picking.id,
                })
                return_action = return_wizard.action_create_returns_all()
                return_picking_id = (
                    return_action.get("res_id")
                    if isinstance(return_action, dict)
                    else False
                )
                if not return_picking_id:
                    raise UserError(
                        _("Failed to create a full return for receipt %s.")
                        % picking.name
                    )

                return_picking = picking_model.browse(return_picking_id)
                return_picking.with_context(
                    skip_chenyang_scan_validation=True,
                    skip_backorder=True,
                ).button_validate()

                if return_picking.state != "done":
                    raise UserError(
                        _("Return picking %s was not completed.")
                        % return_picking.name
                    )

            rec.validate_sunrise_inbound_returned_before_recreate(
                done_picking_list
            )
            rec.validate_sunrise_inbound_packages_empty_before_recreate()
            rec.action_archive_sunrise_packages_before_cancel()
            rec.inbound_order_product_ids.write({
                "package_id": False,
            })
            return_picking_list = picking_model.sudo().search([
                ("return_id", "in", original_picking_list.ids),
            ])
            return_picking_list = rec.get_sunrise_inbound_picking_backorder_chain(
                return_picking_list
            )
            picking_to_detach = (
                done_picking_list | return_picking_list
            ).filtered(lambda picking: picking.inbound_order_id == rec)
            if picking_to_detach:
                picking_to_detach.write({
                    "inbound_order_id": False,
                })

            rec.write({
                "stock_picking_id": False,
                "set_sunrise_inbound_sync": False,
                "set_sunrise_inbound_sync_time": False,
                "sunrise_inbound_sync_error_msg": False,
                "sunrise_inbound_task_number": False,
            })
            rec.message_post(body=_(
                "Prepared receipt recreation. Old receipts: %s. "
                "Completed return pickings were detached. "
                "You can create a receipt manually now."
            ) % original_picking_names)

        return True


    def picking_has_full_done_return(self, picking):
        for rec in self:
            picking.ensure_one()
            done_move_list = picking.move_ids.filtered(
                lambda move: move.state == "done" and not move.scrapped
            )

            for move in done_move_list:
                returned_move_list = move.move_dest_ids.filtered(
                    lambda return_move: return_move.origin_returned_move_id == move
                    and return_move.state == "done"
                )
                returned_qty = sum(returned_move_list.mapped("quantity"))

                if float_compare(
                    returned_qty,
                    move.quantity,
                    precision_rounding=move.product_id.uom_id.rounding,
                ) < 0:
                    return False

        return True

    def validate_sunrise_inbound_auto_return_allowed(self, picking_list):
        move_line_model = self.env["stock.move.line"]
        outbound_line_model = self.env["world.depot.outbound.order.product"]

        for rec in self:
            for picking in picking_list:
                original_move_list = picking.move_ids_without_package.filtered(
                    lambda move: move.state == "done"
                )
                package_list = picking.move_line_ids.filtered(
                    lambda line: line.result_package_id
                ).mapped("result_package_id")
                if not package_list:
                    continue

                outbound_line = outbound_line_model.sudo().search([
                    ("package_id", "in", package_list.ids),
                    ("project", "=", rec.project.id),
                    ("outbound_order_state", "!=", "cancel"),
                ], order="id desc", limit=1)
                if outbound_line:
                    outbound_order = outbound_line.outbound_order_id
                    raise UserError(
                        _(
                            "Inbound pallet %s is referenced by active outbound order %s. "
                            "Please cancel the outbound order before recreating the receipt."
                        )
                        % (
                            outbound_line.package_id.name or outbound_line.package_id.barcode,
                            outbound_order.billno or outbound_order.reference,
                        )
                    )

                used_line = move_line_model.sudo().search([
                    ("package_id", "in", package_list.ids),
                    ("picking_id.state", "!=", "cancel"),
                    ("picking_id.picking_type_id.code", "in", ("outgoing", "internal")),
                ], order="id desc", limit=1).filtered(
                    lambda line: line.move_id.origin_returned_move_id not in original_move_list
                )[:1]
                if used_line:
                    raise UserError(
                        _(
                            "Inbound pallet %s is occupied by %s picking %s in state %s. "
                            "Please cancel or finish the downstream picking first."
                        )
                        % (
                            used_line.package_id.name or used_line.package_id.barcode,
                            used_line.picking_id.picking_type_id.code,
                            used_line.picking_id.name,
                            used_line.picking_id.state,
                        )
                    )

        return True

    def get_sunrise_inbound_picking_backorder_chain(self, picking_list):
        picking_model = self.env["stock.picking"]
        result = picking_model

        for rec in self:
            rec_picking_list = picking_list
            pending_picking_list = picking_list

            while pending_picking_list:
                child_picking_list = picking_model.sudo().search([
                    ("backorder_id", "in", pending_picking_list.ids),
                ])
                child_picking_list -= rec_picking_list
                if not child_picking_list:
                    break

                rec_picking_list |= child_picking_list
                pending_picking_list = child_picking_list

            result |= rec_picking_list

        return result

    def validate_sunrise_inbound_returned_before_recreate(self, picking_list):
        for rec in self:
            for picking in picking_list:
                if not rec.picking_has_full_done_return(picking):
                    raise UserError(
                        _(
                            "Inbound order %s has a completed receipt %s that "
                            "has not been fully returned."
                        )
                        % (rec.reference, picking.name)
                    )
        return True

    def validate_sunrise_inbound_packages_empty_before_recreate(self):
        quant_model = self.env["stock.quant"]

        for rec in self:
            package_names = []
            for pallet_line in rec.inbound_order_product_ids:
                package = pallet_line.package_id
                if not package:
                    continue

                quant_list = quant_model.sudo().search([
                    ("package_id", "=", package.id),
                    ("location_id.usage", "=", "internal"),
                    ("quantity", ">", 0),
                ])
                if quant_list:
                    package_names.append(package.name or package.barcode)

            if package_names:
                raise UserError(
                    _(
                        "Stock remains on original pallets: %s. "
                        "Move or return all stock before recreating."
                    )
                    % ", ".join(sorted(set(package_names)))
                )

        return True
