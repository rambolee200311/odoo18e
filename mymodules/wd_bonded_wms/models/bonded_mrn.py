# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BondedMrn(models.Model):
    _name = 'bonded.mrn'
    _description = 'MRN Number'
    _rec_name = 'mrn'
    _order = 'id desc'

    mrn = fields.Char(string='MRN Number', required=True, copy=False, index=True)
    customs_file_id = fields.Many2one('bonded.customs.file', string='Customs Declaration', required=True, ondelete='cascade', index=True)
    declaration_no = fields.Char(related='customs_file_id.declaration_no', string='Declaration No.', store=True, readonly=True, index=True)
    declaration_type = fields.Selection(related='customs_file_id.declaration_type', string='Declaration Type', store=True, readonly=True, index=True)
    bonded_book_id = fields.Many2one(related='customs_file_id.bonded_book_id', string='Bonded Book', store=True, readonly=True, index=True)
    state = fields.Selection(related='customs_file_id.state', string='Customs Status', store=True, readonly=True, index=True)

    _sql_constraints = [
        ('mrn_uniq', 'unique(mrn)', 'MRN number must be unique!'),
        ('customs_file_uniq', 'unique(customs_file_id)', 'A customs declaration can only have one MRN number!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('mrn'):
                vals['mrn'] = vals['mrn'].strip().upper()
        mrn_records = super().create(vals_list)
        for rec in mrn_records:
            rec.customs_file_id.with_context(skip_mrn_sync=True).write({'mrn_id': rec.id, 'mrn': rec.mrn})
        return mrn_records

    def write(self, vals):
        old_customs_file_ids = self.mapped('customs_file_id')
        if vals.get('mrn'):
            vals['mrn'] = vals['mrn'].strip().upper()
        result = super().write(vals)
        for rec in self:
            rec.customs_file_id.with_context(skip_mrn_sync=True).write({'mrn_id': rec.id, 'mrn': rec.mrn})
        for customs_file in old_customs_file_ids - self.mapped('customs_file_id'):
            if not customs_file.mrn_ids:
                customs_file.with_context(skip_mrn_sync=True).write({'mrn_id': False, 'mrn': False})
        return result

    def unlink(self):
        for rec in self:
            rec.customs_file_id.with_context(skip_mrn_sync=True).write({'mrn_id': False, 'mrn': False})
        return super().unlink()

    @api.constrains('mrn')
    def check_mrn(self):
        pattern = re.compile(r'^\d{2}[A-Z]{2}[A-Z0-9]{14}$')
        # for rec in self:
        #     if not pattern.match(rec.mrn):
        #         raise ValidationError(_('MRN must be 18 characters: 2 digits + 2 letters + 14 letters/digits.'))
