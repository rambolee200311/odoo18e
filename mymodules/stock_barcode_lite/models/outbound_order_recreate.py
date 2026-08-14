from odoo import _, api, fields, models
from odoo.http import request
from odoo.exceptions import UserError, ValidationError
#from odoo.addons.stock_barcode_lite.models.outbound_order_inherit import get_sunrise_outbound_cancel_picking_list

class OutboundOrderRecreate(models.Model):
    _inherit = 'world.depot.outbound.order'

    def action_sunrise_prepare_recreate_outgoing_picking(self):
        picking_model = self.env['stock.picking']
        return_wizard_model= self.env['stock.return.picking']
        for rec in self:
            if not self.env.user.has_group("stock_barcode_lite.group_sunrise_stock_manager"):
                raise UserError(_("Only Sunrise stock managers can recreate pickings."))
            if rec.project.name != "SUNRISE":
                raise UserError (_("Only SUNRISE outbound orders can recreate picking."))
            if rec.state!= 'confirm':
             raise UserError (_("Only confirming outbound orders can be recreated."))

            original_picking_list = (
                    rec.whole_pallet_picking_id | rec.partial_pallet_picking_id
            ).filtered(lambda picking: picking.state != "cancel")
            original_picking_list = rec.get_sunrise_picking_backorder_chain(
                original_picking_list
            )
            if not original_picking_list:
                raise UserError(_("No outbound picking was found for order %s.") % rec.reference)

            return_picking_list = picking_model.sudo().search([
                ("return_id", "in", original_picking_list.ids),
            ])
            return_picking_list = rec.get_sunrise_picking_backorder_chain(return_picking_list)

            pending_return_picking = return_picking_list.filtered(
                lambda picking: picking.state not in ("done", "cancel")
            )[:1]
            if pending_return_picking:
                raise UserError(
                    _("Picking %s has an unfinished return picking or return backorder %s. "
                      "Please finish or cancel it first.")
                    % (
                        pending_return_picking.return_id.name
                        or pending_return_picking.backorder_id.name,
                        pending_return_picking.name,
                    )
                )

            original_picking_names = ", ".join(original_picking_list.mapped("name"))
            done_picking_list = original_picking_list.filtered(lambda picking: picking.state == "done")
            not_done_picking_list = original_picking_list.filtered(
                lambda picking: picking.state not in ("done", "cancel")
            )


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
                return_picking_id = return_action.get("res_id") if isinstance(return_action, dict) else False
                if not return_picking_id:
                    raise UserError(_("Failed to create a full return for picking %s.") % picking.name)

                return_picking = picking_model.browse(return_picking_id)

                # This is an administrator reset operation, so scan checks are skipped.
                return_picking.with_context(
                    skip_chenyang_scan_validation=True,
                    skip_backorder=True,
                ).button_validate()

                if return_picking.state != "done":
                    raise UserError(_("Return picking %s was not completed.") % return_picking.name)

            rec.validate_sunrise_outbound_returned_before_cancel(done_picking_list)

            return_picking_list = picking_model.sudo().search([
                ("return_id", "in", original_picking_list.ids),
            ])

            return_picking_list = rec.get_sunrise_picking_backorder_chain(return_picking_list)

            picking_to_detach = (done_picking_list | return_picking_list).filtered(
                lambda picking: picking.outbound_order_id == rec
            )
            if picking_to_detach:
                picking_to_detach.write({
                    "outbound_order_id": False,
                })

            rec.write({
                "whole_pallet_picking_id": False,
                "partial_pallet_picking_id": False,
                "picking_PICK": False,
                "picking_PICK_date": False,
                "picking_Out": False,
                "picking_Out_date": False,
                "status": "planning",
                "set_sunrise_outbound_sync": False,
                "set_sunrise_outbound_sync_time": False,
                "sunrise_outbound_sync_error_msg": False,
                "sunrise_outbound_task_number": False,
                "set_sunrise_pickup_delivery_sync": False,
                "set_sunrise_pickup_delivery_sync_time": False,
                "sunrise_pickup_delivery_sync_error_msg": False,
            })
            rec.message_post(body=_(
                "Prepared picking recreation. Old pickings: %s. "
                "Completed return pickings were detached. You can create picking manually now."
            ) % original_picking_names)

        return True

    def get_sunrise_picking_backorder_chain(self, picking_list):
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
