# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CustomsFilePreMRN(models.Model):
    _name = 'customs.file.pre.mrn'
    _description = 'B3 Declaration Pre-condition MRN - 前置MRN中间表'
    _rec_name = 'mrn'
    _order = 'customs_file_id, id'

    customs_file_id = fields.Many2one('bonded.customs.file', string='B3 Customs Declaration',
                                      required=True, ondelete='cascade', index=True)
    mrn_id = fields.Many2one('bonded.mrn', string='MRN Number', ondelete='restrict', index=True)
    mrn = fields.Char(string='MRN Number', readonly=True, index=True, help='Legacy compatibility mirror of MRN Number.')
    t1_customs_file_id = fields.Many2one('bonded.customs.file', related='mrn_id.customs_file_id', string='T1 Customs Declaration', store=True, readonly=True, index=True)
    status = fields.Selection([
        ('pending', 'Pending Closure'),
        ('closed', 'Closed'),
    ], string='Status', default='pending', required=True)
    satisfied_date = fields.Datetime(string='Satisfied Date', readonly=True)
    gate_arrival_ids = fields.One2many('gate.arrival', 'pre_mrn_t1_id', string='Gate Arrivals',
                                       help='Containers under this T1 MRN. One2many enforced (one container = one MRN).')
    remark = fields.Text(string='Remark')

    _sql_constraints = [
        ('mrn_id_uniq_per_declaration', 'unique(customs_file_id, mrn_id)',
         'MRN must be unique per B3 declaration!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('mrn_id'):
                raise ValidationError(_('Select an MRN Number before creating a B3 pre-condition.'))
            mrn_record = self.env['bonded.mrn'].sudo().browse(vals['mrn_id'])
            if mrn_record.declaration_type != 't1_in':
                raise ValidationError(_('B3 pre-condition MRN must belong to a T1 inbound customs declaration.'))
            vals['mrn'] = mrn_record.mrn
            if mrn_record.state == 'done':
                vals['status'] = 'closed'
                vals['satisfied_date'] = mrn_record.customs_file_id.t1_closed_date
        records = super().create(vals_list)
        return records

    def write(self, vals):
        if vals.get('mrn_id'):
            mrn_record = self.env['bonded.mrn'].sudo().browse(vals['mrn_id'])
            if mrn_record.declaration_type != 't1_in':
                raise ValidationError(_('B3 pre-condition MRN must belong to a T1 inbound customs declaration.'))
            vals['mrn'] = mrn_record.mrn
        return super().write(vals)

    def ensure_mrn_id(self):
        env_bonded_customs_file = self.env['bonded.customs.file'].sudo()
        for rec in self:
            if rec.mrn_id or not rec.mrn:
                continue
            t1_customs_file = env_bonded_customs_file.search([('mrn', '=', rec.mrn), ('declaration_type', '=', 't1_in')], limit=1)
            if t1_customs_file:
                t1_customs_file.ensure_mrn_record()
                rec.write({'mrn_id': t1_customs_file.mrn_id.id})
        return self
