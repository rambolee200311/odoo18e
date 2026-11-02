# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_dg = fields.Boolean(string='Dangerous Goods')
    un_code = fields.Char(string='UN Code', help='The UN Code for dangerous goods, if applicable')
    pcs_per_pallet = fields.Integer(string='Pcs/Pallet', default=1)
    duty_rate = fields.Float(string='Duty Rate (%)', default=0.0)
    brand = fields.Char(string='Brand')
    gross_weight = fields.Float(string='Gross Weight (kg)', copy=False)
    product_dimensions = fields.Char(string='Product Dimensions (m)', copy=False)
    organic = fields.Boolean(string='Organic', default=False, copy=False, index=True)
