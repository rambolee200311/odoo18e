from odoo import models, fields, api
from odoo.exceptions import ValidationError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    bill_of_lading = fields.Char('Bill of Lading')
    cntrno = fields.Char('Container Number')
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
        res = super().button_validate()
        if (self.picking_type_id.code == 'incoming'):  # 'incoming' corresponds to Receipt operation type
            for move_line in self.move_line_ids:
                if (not move_line.lot_id.bill_of_lading
                        and not move_line.lot_id.cntrno):
                    move_line.lot_id.write({
                        'bill_of_lading': self.bill_of_lading,
                        'cntrno': self.cntrno
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
            #for move_line in picking.move_line_ids:
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
