
from odoo import models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare

class OutboundOrder(models.Model):
    _inherit = 'world.depot.outbound.order'

    def picking_has_full_done_return(self, picking):
        picking.ensure_one()

        done_moves = picking.move_ids.filtered(lambda rec: rec.state == 'done' and not rec.scrapped)
        for move in done_moves:
            return_moves = move.move_dest_ids.filtered(
                lambda rec: rec.origin_returned_move_id == move and rec.state == 'done'
            )
            returned_quantity = sum(return_moves.mapped('quantity'))

            if float_compare(
                    returned_quantity,
                    move.quantity,
                    precision_rounding=move.product_id.uom_id.rounding,
            ) < 0:
                return False

        return True

    def action_prepare_recreate_picking(self):
        if not self.env.user.has_group('stock.group_stock_manager') and not self.env.user.has_group(
                'base.group_system'):
            raise UserError(_("Only stock managers can prepare recreate picking."))
        if self.project and self.project.name.lower() != 'hoymiles':
            raise UserError(_("Only Hoymiles project can prepare recreate picking."))
        picking_env = self.env['stock.picking']

        for rec in self:
            if rec.state != 'confirm':
                raise UserError(_("Only confirmed outbound orders can prepare recreate picking."))

            old_pick = rec.picking_PICK
            if not old_pick:
                continue

            outgoing_pickings = rec.picking_Out
            searched_outgoing_ids = picking_env.sudo().search([
                ('origin', '=', old_pick.name),
                ('picking_type_code', '=', 'outgoing'),
            ]).ids
            outgoing_pickings |= picking_env.browse(searched_outgoing_ids)

            picking_chain = old_pick | outgoing_pickings
            done_pickings = picking_chain.filtered(lambda picking: picking.state == 'done')

            for picking in done_pickings:
                if not rec.picking_has_full_done_return(picking):
                    raise UserError(_(
                        "Picking %s is done. Please create and validate its return picking first."
                    ) % picking.name)

            cancel_pickings = picking_chain.filtered(lambda picking: picking.state not in ('done', 'cancel'))
            for picking in cancel_pickings:
                picking.action_cancel()

            return_picking_ids = picking_env.sudo().search([
                ('return_id', 'in', picking_chain.ids),
            ]).ids
            return_pickings = picking_env.browse(return_picking_ids)

            detach_pickings = (picking_chain | return_pickings).filtered(
                lambda picking: picking.outbound_order_id == rec
            )
            if detach_pickings:
                detach_pickings.write({'outbound_order_id': False})

            rec.write({
                'picking_PICK': False,
                'picking_PICK_date': False,
                'picking_Out': False,
                'picking_Out_date': False,
                'status': 'planning',
                'set_status_to_pick_finished': False,
                'set_status_to_pick_finished_time': False,
                'status_to_pick_finished_error_msg': False,
                'set_outbound_pack_sync': False,
                'set_outbound_pack_sync_time': False,
                'outbound_pack_sync_error_msg': False,
                'set_outbound_result_sync': False,
                'set_outbound_result_sync_time': False,
                'outbound_result_sync_error_msg': False,

                'status_to_pick_finished_time_user': False,
                'outbound_pack_sync_time_user': False,
                'outbound_result_sync_time_user': False,
            })

            rec.message_post(body=_(
                "Old picking chain was cleaned. Old picking: %s. You can create picking manually now."
            ) % old_pick.name)

        return True
