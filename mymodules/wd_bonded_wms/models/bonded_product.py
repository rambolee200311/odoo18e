# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class BondedProduct(models.Model):
    _name = 'bonded.product'
    _description = 'Bonded Product Filing - 保税商品备案'
    _rec_name = 'product_id'
    _order = 'bonded_book_id, product_id'

    bonded_book_id = fields.Many2one('bonded.book', string='Bonded Book', required=True,
                                     ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', string='Product', required=True,
                                 ondelete='restrict')
    hs_code = fields.Char(string='HS Code', required=True)
    declared_unit_price = fields.Monetary(string='Declared Unit Price', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.ref('base.EUR').id,
                                  required=True)
    uom_id = fields.Many2one('uom.uom', string='UoM', required=True)
    supervision_conditions = fields.Char(string='Supervision Conditions',
                                         help='e.g. License required, quota restrictions')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, index=True)

    _sql_constraints = [
        ('product_uniq_per_book', 'unique(bonded_book_id, product_id)',
         'Product already exists in this bonded book!'),
    ]

    def action_activate(self):
        self.state = 'active'

    def action_cancel(self):
        self.state = 'cancelled'