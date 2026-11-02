# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


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
    reserved_value = fields.Monetary(string='Reserved Value', compute='_compute_value_summary', store=True, readonly=True)
    available_value = fields.Monetary(string='Available Value', compute='_compute_value_summary', store=True, readonly=True)
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
    value_ledger_ids = fields.One2many('bonded.value.ledger', 'bonded_book_id', string='Value Ledger')

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

    @api.depends('company_total_value_limit', 'value_ledger_ids.reserved_change', 'value_ledger_ids.deducted_change')
    def _compute_value_summary(self):
        env_value_ledger = self.env['bonded.value.ledger'].sudo()
        for rec in self:
            ledger_records = env_value_ledger.search([('bonded_book_id', '=', rec.id)])
            rec.reserved_value = sum(ledger_records.mapped('reserved_change'))
            rec.available_value = rec.company_total_value_limit - rec.reserved_value - sum(ledger_records.mapped('deducted_change'))

    def check_available_value(self, value_amount, project_id=False):
        env_value_ledger = self.env['bonded.value.ledger'].sudo()
        env_bonded_value_limit = self.env['bonded.value.limit'].sudo()
        for rec in self:
            ledger_records = env_value_ledger.search([('bonded_book_id', '=', rec.id)])
            reserved_value = sum(ledger_records.mapped('reserved_change'))
            deducted_value = sum(ledger_records.mapped('deducted_change'))
            if rec.company_total_value_limit - reserved_value - deducted_value < value_amount:
                raise UserError(_('The available value is insufficient for this document.'))
            if project_id:
                today = fields.Date.today()
                project_limit = env_bonded_value_limit.search([
                    ('bonded_book_id', '=', rec.id), ('project_id', '=', project_id), ('state', '=', 'active'),
                    ('effective_date', '<=', today), '|', ('expiry_date', '=', False), ('expiry_date', '>=', today),
                ], order='effective_date desc, id desc', limit=1)
                if project_limit:
                    project_ledger_records = env_value_ledger.search([('bonded_book_id', '=', rec.id), ('project_id', '=', project_id)])
                    project_used_value = sum(project_ledger_records.mapped('reserved_change')) + sum(project_ledger_records.mapped('deducted_change'))
                    if project_limit.total_value - project_used_value < value_amount:
                        raise UserError(_('The available value for project %s is insufficient for this document.') % project_limit.project_id.display_name)
        return True

    def create_value_ledger(self, operation_type, value_amount, project_id=False, inbound_id=False, outbound_id=False, customs_file_id=False, release_from_deduction=False):
        ledger_records = self.env['bonded.value.ledger']
        env_value_ledger = self.env['bonded.value.ledger'].sudo()
        for rec in self:
            if value_amount <= 0:
                continue
            reserved_change = 0.0
            deducted_change = 0.0
            if operation_type == 'reserve':
                reserved_change = value_amount
            elif operation_type == 'deduct':
                reserved_change = -value_amount
                deducted_change = value_amount
            elif operation_type == 'release':
                if release_from_deduction:
                    deducted_change = -value_amount
                else:
                    reserved_change = -value_amount
            else:
                raise UserError(_('Unsupported value ledger operation.'))
            book_ledger_records = env_value_ledger.search([('bonded_book_id', '=', rec.id)])
            reserved_value = sum(book_ledger_records.mapped('reserved_change')) + reserved_change
            deducted_value = sum(book_ledger_records.mapped('deducted_change')) + deducted_change
            ledger_records |= self.env['bonded.value.ledger'].create({
                'bonded_book_id': rec.id,
                'project_id': project_id,
                'inbound_id': inbound_id,
                'outbound_id': outbound_id,
                'customs_file_id': customs_file_id,
                'operation_type': operation_type,
                'value_amount': value_amount,
                'reserved_change': reserved_change,
                'deducted_change': deducted_change,
                'reserved_value_after': reserved_value,
                'available_value_after': rec.company_total_value_limit - reserved_value - deducted_value,
            })
        return ledger_records

    def reserve_document_value(self, value_amount, project_id=False, inbound_id=False, outbound_id=False):
        for rec in self:
            rec.check_available_value(value_amount, project_id=project_id)
            rec.create_value_ledger('reserve', value_amount, project_id=project_id, inbound_id=inbound_id, outbound_id=outbound_id)
        return True

    def deduct_document_value(self, project_id=False, inbound_id=False, outbound_id=False, customs_file_id=False):
        env_value_ledger = self.env['bonded.value.ledger'].sudo()
        for rec in self:
            domain = [('bonded_book_id', '=', rec.id)]
            if inbound_id:
                domain.append(('inbound_id', '=', inbound_id))
            if outbound_id:
                domain.append(('outbound_id', '=', outbound_id))
            ledger_records = env_value_ledger.search(domain)
            reserved_value = sum(ledger_records.mapped('reserved_change'))
            if reserved_value > 0:
                rec.create_value_ledger('deduct', reserved_value, project_id=project_id, inbound_id=inbound_id, outbound_id=outbound_id, customs_file_id=customs_file_id)
        return True

    def release_document_value(self, project_id=False, inbound_id=False, outbound_id=False, customs_file_id=False):
        env_value_ledger = self.env['bonded.value.ledger'].sudo()
        for rec in self:
            domain = [('bonded_book_id', '=', rec.id)]
            if inbound_id:
                domain.append(('inbound_id', '=', inbound_id))
            if outbound_id:
                domain.append(('outbound_id', '=', outbound_id))
            ledger_records = env_value_ledger.search(domain)
            reserved_value = sum(ledger_records.mapped('reserved_change'))
            deducted_value = sum(ledger_records.mapped('deducted_change'))
            if reserved_value > 0:
                rec.create_value_ledger('release', reserved_value, project_id=project_id, inbound_id=inbound_id, outbound_id=outbound_id, customs_file_id=customs_file_id)
            elif deducted_value > 0:
                rec.create_value_ledger('release', deducted_value, project_id=project_id, inbound_id=inbound_id, outbound_id=outbound_id, customs_file_id=customs_file_id, release_from_deduction=True)
        return True

    def action_activate(self):
        self.state = 'active'

    def action_expire(self):
        self.state = 'expired'

    def action_cancel(self):
        self.state = 'cancelled'
