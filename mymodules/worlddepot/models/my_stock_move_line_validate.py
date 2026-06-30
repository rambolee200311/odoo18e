from odoo import models, api, _
from odoo.exceptions import UserError, ValidationError

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def write(self, vals):
        """Prevent changing move line locations for already-processed operations.

        Behaviour:
        - If `validation_in_progress` context flag is present, defer to super().
        - If `location_id`/`location_dest_id` are present in `vals`, perform a
          per-record write: for move_lines whose parent move is in state 'done'
          drop the location keys; for others apply the full `vals`.
        """
        if self.env.context.get('validation_in_progress'):
            return super().write(vals)

        location_keys = {'location_id', 'location_dest_id'}
        if not any(k in vals for k in location_keys):
            return super().write(vals)

        result = True
        for ml in self:
            parent_move = ml.move_id
            if parent_move and parent_move.state == 'done':
                filtered_vals = {k: v for k, v in vals.items() if k not in location_keys}
                if filtered_vals:
                    try:
                        res = super(StockMoveLine, ml).write(filtered_vals)
                    except ValidationError as e:
                        if self.env.context.get('ignore_valuation_check'):
                            _logger.warning('Ignored valuation ValidationError while writing move line %s: %s', ml.id, e)
                            res = True
                        else:
                            raise
                    result = result and res
                else:
                    _logger.debug('Skipping location change on done move line %s', ml.id)
                    result = result and True
            else:
                try:
                    res = super(StockMoveLine, ml).write(vals)
                except ValidationError as e:
                    if self.env.context.get('ignore_valuation_check'):
                        _logger.warning('Ignored valuation ValidationError while writing move line %s: %s', ml.id, e)
                        res = True
                    else:
                        raise
                result = result and res

        return result

    def _action_done(self):
        """Store original locations before completion"""
        for move_line in self:
            move = move_line.move_id
            if move:
                if not move.original_location_id:
                    move.original_location_id = move_line.location_id.id
                if not move.original_location_dest_id:
                    move.original_location_dest_id = move_line.location_dest_id.id
        
        return super()._action_done()