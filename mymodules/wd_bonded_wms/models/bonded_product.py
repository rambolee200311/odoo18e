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
                                 ondelete='restrict', index=True)
    hs_code = fields.Char(string='HS Code', required=True)
    declared_unit_price = fields.Monetary(string='Declared Unit Price', required=True)
    goods_value = fields.Monetary(string='Goods Value')
    customs_code = fields.Char(string='Customs Code')
    article_number = fields.Char(string='Article Number')
    product_description = fields.Char(string='Product Description')
    technical_description = fields.Text(string='Technical Description')
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

    @api.model_create_multi
    def create(self, vals_list):
        env_product = self.env['product.product'].sudo()
        for vals in vals_list:
            product = env_product.browse(vals.get('product_id')).exists()
            if not product:
                continue
            vals.setdefault('goods_value', product.goods_value)
            vals.setdefault('customs_code', product.customs_code)
            vals.setdefault('article_number', product.article_number)
            vals.setdefault('product_description', product.product_description)
            vals.setdefault('technical_description', product.technical_description)
        return super().create(vals_list)

    @api.onchange('product_id')
    def onchange_product_id(self):
        for rec in self:
            product = rec.product_id.sudo()
            rec.goods_value = product.goods_value
            rec.customs_code = product.customs_code
            rec.article_number = product.article_number
            rec.product_description = product.product_description
            rec.technical_description = product.technical_description

    def action_activate(self):
        self.state = 'active'

    def action_cancel(self):
        self.state = 'cancelled'
