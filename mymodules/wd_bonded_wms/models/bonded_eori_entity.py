# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BondedEoriEntity(models.Model):
    _name = 'bonded.eori.entity'
    _description = 'Bonded EORI Entity'
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(string='Entity Name', required=True, index=True)
    partner_id = fields.Many2one('res.partner', string='Commercial Partner', required=True, ondelete='restrict', index=True)
    eori_no = fields.Char(string='EORI Number', required=True, index=True)
    country_id = fields.Many2one('res.country', string='Country', required=True, ondelete='restrict', index=True)
    eori_valid_until = fields.Date(string='EORI Valid Until', index=True)
    customs_office_code = fields.Char(string='Customs Office Code', index=True)
    customs_authorization_lines = fields.One2many('bonded.customs.authorization', 'eori_entity_id', string='Customs Authorizations')
    state = fields.Selection([('active', 'Active'), ('inactive', 'Inactive')], string='Status', default='active', required=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company, index=True)

    _sql_constraints = [
        ('eori_no_company_uniq', 'unique(eori_no, company_id)', 'EORI number must be unique per company!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('eori_no'):
                vals['eori_no'] = vals['eori_no'].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('eori_no'):
            vals['eori_no'] = vals['eori_no'].strip().upper()
        return super().write(vals)

    @api.constrains('eori_no')
    def check_eori_no(self):
        pattern = re.compile(r'^[A-Z]{2}[A-Z0-9]{2,15}$')
        for rec in self:
            if rec.eori_no and not pattern.match(rec.eori_no):
                raise ValidationError(_('EORI number format is invalid.'))

    def validate_active_on_date(self, check_date=None):
        check_date = check_date or fields.Date.today()
        for rec in self:
            if rec.state != 'active':
                raise ValidationError(_('EORI entity %s is not active.') % rec.display_name)
            if rec.eori_valid_until and rec.eori_valid_until < check_date:
                raise ValidationError(_('EORI entity %s is expired.') % rec.display_name)
        return True
