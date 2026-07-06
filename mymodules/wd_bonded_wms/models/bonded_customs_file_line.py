# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class BondedCustomsFileLine(models.Model):
    _name = 'bonded.customs.file.line'
    _description = 'Customs Declaration Line - 海关文件行项 (SAD/C88 Box6~Box38)'
    _order = 'customs_file_id, item_no'

    customs_file_id = fields.Many2one('bonded.customs.file', string='Customs Declaration',
                                      required=True, ondelete='cascade', index=True)
    item_no = fields.Integer(string='Item No. (Box6)', required=True, default=1)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    hs_code = fields.Char(string='HS Code (CN8, Box33)', required=True)
    origin_country_id = fields.Many2one('res.country', string='Country of Origin (Box34)', required=True)
    gross_weight = fields.Float(string='Gross Weight (Box35)', required=True, default=0.0)
    net_weight = fields.Float(string='Net Weight (Box38)', required=True, default=0.0)
    line_value = fields.Monetary(string='Line Value', required=True, default=0.0)
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.ref('base.EUR').id)
    quantity = fields.Float(string='Quantity', required=True, default=1.0)
    uom_id = fields.Many2one('uom.uom', string='UoM', required=True)
    marks_numbers = fields.Text(string='Marks & Numbers')
    initial_customs_status = fields.Selection([
        ('entrepot', 'Entrepot (Bonded)'),
        ('vrij', 'Vrij (Free Circulation)'),
        ('rto', 'RTO (Return to Origin)'),
        ('in_t1_transit', 'In T1 Transit'),
    ], string='Initial Customs Status', required=True, default='entrepot')
    remark = fields.Text(string='Remark')