# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    is_dg = fields.Boolean(string='Dangerous Goods', readonly=True)
    un_code = fields.Char(string='UN Code', readonly=True)
    pcs_per_pallet = fields.Integer(string='Pcs/Pallet', store=True, readonly=True)
    duty_rate = fields.Float(string='Duty Rate (%)', default=0.0)
    brand = fields.Char(string='Brand')
    # origin_country = fields.Many2one('res.country', string='Country of Origin', tracking=True, index=True)
    goods_value = fields.Monetary(string='Goods Value', currency_field='currency_id', tracking=True)
    hs_code = fields.Char(string='HS Code', tracking=True, index=True)
    customs_code = fields.Char(string='Customs Code', tracking=True, index=True)
    article_number = fields.Char(string='Article Number', tracking=True, index=True)
    product_description = fields.Char(string='Product Description', tracking=True)
    technical_description = fields.Text(string='Technical Description', tracking=True)
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)
    adr_class_name = fields.Char(string='ADR Class Name')
    adr_packing_group = fields.Selection([('I', 'I'), ('II', 'II'), ('III', 'III'), ('none', 'N/A')], string='ADR Packing Group')
    adr_class = fields.Char(string='ADR Class/Division')
