from odoo import fields, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    gross_weight = fields.Float(string='Gross Weight (kg)', copy=False)
    product_dimensions = fields.Char(string='Product Dimensions (m)', copy=False)
