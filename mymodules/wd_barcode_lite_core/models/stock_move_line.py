from odoo import fields, models


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    is_location_updated = fields.Boolean(string='Location Updated', default=False, copy=False, index=True)
    location_updated_by_id = fields.Many2one('res.users', string='Location Updated By', copy=False)
    location_updated_datetime = fields.Datetime(string='Location Updated Datetime', copy=False)
    is_outbound_scanned = fields.Boolean(string='Outbound Scanned', default=False, copy=False, index=True)
    outbound_scanned_quantity = fields.Float(string='Outbound Scanned Quantity', default=0.0, copy=False)
    outbound_scanned_by_id = fields.Many2one('res.users', string='Outbound Scanned By', copy=False)
    outbound_scanned_datetime = fields.Datetime(string='Outbound Scanned Datetime', copy=False)
