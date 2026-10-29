# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


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
    eori_entity_id = fields.Many2one('bonded.eori.entity', string='EORI Entity', required=True,
                                     ondelete='restrict', index=True)
    consignor_company = fields.Many2one('res.partner', string='Consignor Company')
    consignee_company = fields.Many2one('res.partner', string='Consignee Company')
    valid_from = fields.Date(string='Valid From', required=True)
    valid_until = fields.Date(string='Valid Until', required=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', string='Currency', readonly=True)
    company_total_value_limit = fields.Monetary(string='Company Total Value Limit', required=True, default=0.0)
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
    ledger_lines = fields.One2many('bonded.book.line', 'bonded_book_id', string='Ledger Lines')

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

    @api.constrains('company_total_value_limit')
    def check_company_total_value_limit(self):
        env_bonded_value_limit = self.env['bonded.value.limit'].sudo()
        for rec in self:
            project_limit = env_bonded_value_limit.search([
                ('bonded_book_id', '=', rec.id),
                ('total_value', '>', rec.company_total_value_limit),
            ], limit=1)
            if project_limit:
                raise ValidationError(_('A project value limit cannot exceed the company total value limit.'))

    def action_activate(self):
        self.state = 'active'

    def action_expire(self):
        self.state = 'expired'

    def action_cancel(self):
        self.state = 'cancelled'
