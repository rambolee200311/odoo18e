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
    uom_id = fields.Many2one('uom.uom', string='UoM', related='product_id.uom_id', readonly=True)
    eligible_product_ids = fields.Many2many('product.product', compute='_compute_eligible_product_ids')
    marks_numbers = fields.Text(string='Marks & Numbers')
    initial_customs_status = fields.Selection([
        ('entrepot', 'Entrepot (Bonded)'),
        ('vrij', 'Vrij (Free Circulation)'),
        ('rto', 'RTO (Return to Origin)'),
        ('in_t1_transit', 'In T1 Transit'),
    ], string='Initial Customs Status', required=True, default='entrepot')
    remark = fields.Text(string='Remark')

    @api.depends('customs_file_id.bonded_book_id')
    def _compute_eligible_product_ids(self):
        for rec in self:
            book = rec.customs_file_id.bonded_book_id
            filings = self.env['bonded.product'].sudo().search([
                ('bonded_book_id', '=', book.id),
                ('state', '=', 'active'),
            ]) if book else self.env['bonded.product']
            rec.eligible_product_ids = filings.mapped('product_id')

    @api.depends('customs_file_id.declaration_no', 'item_no', 'product_id.display_name', 'hs_code', 'quantity', 'uom_id.display_name')
    def _compute_display_name(self):
        for rec in self:
            parts = []
            if rec.customs_file_id.declaration_no:
                parts.append(rec.customs_file_id.declaration_no)
            if rec.item_no:
                parts.append('#%s' % rec.item_no)
            if rec.product_id:
                parts.append(rec.product_id.display_name)
            if rec.hs_code:
                parts.append('HS %s' % rec.hs_code)
            if rec.quantity:
                quantity = f'{rec.quantity:g}'
                if rec.uom_id:
                    quantity = f'{quantity} {rec.uom_id.display_name}'
                parts.append(quantity)
            rec.display_name = ' / '.join(parts) or str(rec.id)
