from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import float_is_zero, float_compare


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    bill_of_lading = fields.Char('Bill of Lading')
    cntrno = fields.Char('Container Number')
    ref_1 = fields.Char('Reference 1', help='Additional reference field for custom use')
    ref_2 = fields.Char('Reference 2', help='Additional reference field for custom use')
    planning_date = fields.Datetime('Planning Date', help='Date when the picking is planned to be processed')
    inbound_order_id = fields.Many2one(
        comodel_name='world.depot.inbound.order',
        string='Inbound Order',
        help='Reference to the related Inbound Order',
        readonly=True
    )
    outbound_order_id = fields.Many2one(
        comodel_name='world.depot.outbound.order',
        string='Outbound Order',
        help='Reference to the related Outbound Order',
        readonly=True
    )
    load_ref = fields.Char(string='Loading Reference', required=False, help='Reference for the Delivery', )

    '''
    @api.constrains('bill_of_lading', 'cntrno', 'picking_type_id', 'origin_returned_picking_id')
    def _check_receipt_fields(self):
        for record in self:
            if (record.picking_type_id.code == 'incoming'
                    and not record.origin_returned_picking_id):  # 'incoming' corresponds to Receipt operation type
                if not record.bill_of_lading or not record.cntrno:
                    raise ValidationError("Bill of Lading and Container Number cannot be empty for Receipt operations.")
    '''

    def button_validate(self):
        # Check strict quantity control for each picking
        for picking in self:
            if picking.picking_type_id.strict_quantity_control:
                for move in picking.move_ids:
                    if move.state in ('done', 'cancel'):
                        continue
                    # if not float_is_zero(move.product_uom_qty, precision_rounding=move.product_uom.rounding):
                        # Use move.quantity instead of quantity_done
                        if float_compare(move.quantity, move.product_uom_qty,
                                         precision_rounding=move.product_uom.rounding) != 0:
                            raise UserError(_(
                                "Actual quantity must equal demand quantity for product %s.\n"
                                "Demand: %s %s, Actual: %s %s\n\n"
                                "This is enforced by the operation type: %s"
                            ) % (
                                                move.product_id.display_name,
                                                move.product_uom_qty,
                                                move.product_uom.name,
                                                move.quantity,  # Now shows actual done quantity
                                                move.product_uom.name,
                                                picking.picking_type_id.name
                                            ))

        res = super().button_validate()
        if (self.picking_type_id.code == 'incoming'):  # 'incoming' corresponds to Receipt operation type
            for move_line in self.move_line_ids:
                if (not move_line.lot_id.bill_of_lading
                        and not move_line.lot_id.cntrno):
                    move_line.lot_id.write({
                        'bill_of_lading': self.bill_of_lading,
                        'cntrno': self.cntrno
                    })

            if self.inbound_order_id:
                # Update the inbound order with date_done
                self.inbound_order_id.write({
                    'i_date': self.date_done,
                })
        return res

    # resetting their state to "draft"
    def delete_done_pickings(self):
        # Prompt user for confirmation
        action = {
            'type': 'ir.actions.act_window',
            'name': 'Confirm Deletion',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_message': 'Are you sure you want to delete all done pickings?',
                'default_confirm_action': 'delete_done_pickings_confirm',
            },
        }
        return action

    def delete_done_pickings_confirm(self):
        """Delete pickings in 'done' state after resetting their state and cleaning related records."""
        done_pickings = self.search([('state', '=', 'done')])
        for picking in done_pickings:
            # Reset state of stock moves and move lines
            for move in picking.move_ids:
                move.state = 'draft'
            for move_line in picking.move_line_ids:
                move_line.state = 'draft'
            # Skip deletion of quants due to access restrictions
            # You can log or handle quants differently if needed
            # Handle related quants
            # for move_line in picking.move_line_ids:
            #    quants = self.env['stock.quant'].search([('lot_id', '=', move_line.lot_id.id)])
            #    quants.unlink()  # Delete related quants

            # Forcefully reset picking state to 'draft'
            picking.state = 'draft'

            # Unlink the picking
            picking.unlink()


# models/stock_lot.py
class StockLot(models.Model):
    _inherit = 'stock.lot'

    bill_of_lading = fields.Char('Bill of Lading')
    cntrno = fields.Char('Container Number')


class StockLocation(models.Model):
    _inherit = 'stock.location'

    def _get_removal_strategy_order(self, removal_strategy):
        if removal_strategy == 'fifo':
            # 改为按时间戳升序排列
            return 'date, id'
        return super(StockLocation, self)._get_removal_strategy_order(removal_strategy)


class StockMove(models.Model):
    _inherit = 'stock.move'

    # InboundOrderProductsOfPallet's ID
    inbound_order_product_pallet_id = fields.Integer('Inbound Order Product Pallet ID', )
    nine_digit_linglong_code = fields.Char(
        string="Nine Digit Linglong Code",
        related='product_id.nine_digit_linglong_code',
        store=True
    )

    def _prepare_merge_moves_distinct_fields(self):
        distinct_fields = super()._prepare_merge_moves_distinct_fields()
        # Only use pallet_id if set; ignore when null
        distinct_fields.append('inbound_order_product_pallet_id')
        return distinct_fields
'''
    def _merge_moves_fields(self):
        vals = super()._merge_moves_fields()
        vals['product_uom_qty'] = self[0].product_uom_qty  # 禁用数量合并
        return vals
'''
