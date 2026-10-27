# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BondedCustomsAuthorization(models.Model):
    _name = 'bonded.customs.authorization'
    _description = 'Bonded Customs Authorization'
    _rec_name = 'auth_no'
    _order = 'id desc'

    eori_entity_id = fields.Many2one('bonded.eori.entity', string='EORI Entity', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', string='Commercial Partner', index=True)
    auth_type = fields.Selection([
        ('eori', 'EORI'),
        ('c510', 'C510 Bonded Warehouse'),
        ('article_23_vat_deferment', 'Article 23 VAT Deferment'),
        ('aeo', 'AEO'),
        ('import_license', 'Import License'),
        ('export_license', 'Export License'),
        ('other', 'Other'),
    ], string='Authorization Type', required=True, index=True)
    auth_no = fields.Char(string='Authorization No.', required=True, index=True)
    valid_from = fields.Date(string='Valid From', required=True, index=True)
    valid_until = fields.Date(string='Valid Until', required=True, index=True)
    state = fields.Selection([('active', 'Active'), ('expired', 'Expired'), ('cancelled', 'Cancelled')], string='Status', default='active', required=True, index=True)
    certificate_file = fields.Binary(string='Certificate File', attachment=True)
    certificate_filename = fields.Char(string='Certificate Filename')
    remark = fields.Text(string='Remark')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('eori_entity_id') and not vals.get('partner_id'):
                entity = self.env['bonded.eori.entity'].sudo().browse(vals['eori_entity_id'])
                vals['partner_id'] = entity.partner_id.id
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('eori_entity_id'):
            entity = self.env['bonded.eori.entity'].sudo().browse(vals['eori_entity_id'])
            vals['partner_id'] = entity.partner_id.id
        return super().write(vals)

    @api.constrains('valid_from', 'valid_until')
    def check_valid_dates(self):
        for rec in self:
            if rec.valid_from and rec.valid_until and rec.valid_from > rec.valid_until:
                raise ValidationError(_('Valid From cannot be later than Valid Until.'))

    def check_active_on_date(self, check_date=None):
        check_date = check_date or fields.Date.today()
        for rec in self:
            if rec.state != 'active' or rec.valid_from > check_date or rec.valid_until < check_date:
                raise ValidationError(_('Customs authorization %s is not valid on %s.') % (rec.auth_no, check_date))
        return True
