# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class BondedBook(models.Model):
    _name = 'bonded.book'
    _description = 'Bonded Book - 保税账册'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(string='Book No.', required=True, copy=False,
                       default=lambda self: _('New'), readonly=True, index=True)
    customs_office_code = fields.Char(string='Customs Office Code', required=True, index=True,
                                      help='e.g. NLRTM')
    operator_company = fields.Many2one('res.partner', string='Operator Company', required=True,
                                       domain=[('company_type', '=', 'company')])
    consignor_company = fields.Many2one('res.partner', string='Consignor Company')
    consignee_company = fields.Many2one('res.partner', string='Consignee Company')
    valid_from = fields.Date(string='Valid From', required=True)
    valid_until = fields.Date(string='Valid Until', required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True, index=True)

    # 关联
    value_limit_ids = fields.One2many('bonded.value.limit', 'bonded_book_id', string='Value Limits')
    bonded_product_ids = fields.One2many('bonded.product', 'bonded_book_id', string='Bonded Products')
    customs_file_ids = fields.One2many('bonded.customs.file', 'bonded_book_id', string='Customs Declarations')

    # 配置
    shortage_threshold_percent = fields.Float(string='Shortage Threshold (%)', default=1.0,
                                              help='Override global shortage threshold for this book')
    shortage_threshold_amount = fields.Float(string='Shortage Threshold (EUR)', default=500.0,
                                             help='Override global shortage amount for this book')

    description = fields.Text(string='Description')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    _sql_constraints = [
        ('name_uniq', 'unique(name, company_id)', 'Book number must be unique per company!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('seq.bonded.book') or _('New')
        return super().create(vals_list)

    def action_activate(self):
        self.state = 'active'

    def action_expire(self):
        self.state = 'expired'

    def action_cancel(self):
        self.state = 'cancelled'