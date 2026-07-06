# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class CustomsFilePreMRN(models.Model):
    _name = 'customs.file.pre.mrn'
    _description = 'B3 Declaration Pre-condition MRN - 前置MRN中间表'
    _rec_name = 'mrn'
    _order = 'customs_file_id, id'

    customs_file_id = fields.Many2one('bonded.customs.file', string='B3 Customs Declaration',
                                      required=True, ondelete='cascade', index=True)
    mrn = fields.Char(string='MRN Number', required=True, index=True)
    t1_customs_file_id = fields.Many2one('bonded.customs.file', string='T1 Customs Declaration',
                                         help='Auto-linked via MRN lookup')
    status = fields.Selection([
        ('pending', 'Pending Closure'),
        ('closed', 'Closed'),
    ], string='Status', default='pending', required=True)
    satisfied_date = fields.Datetime(string='Satisfied Date', readonly=True)
    gate_arrival_ids = fields.One2many('gate.arrival', 'pre_mrn_t1_id', string='Gate Arrivals',
                                       help='Containers under this T1 MRN. One2many enforced (one container = one MRN).')
    remark = fields.Text(string='Remark')

    _sql_constraints = [
        ('mrn_uniq_per_declaration', 'unique(customs_file_id, mrn)',
         'MRN must be unique per B3 declaration!'),
    ]

    @api.model
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.mrn:
                # Auto-link to T1 customs file
                t1_file = self.env['bonded.customs.file'].search([
                    ('mrn', '=', rec.mrn),
                    ('declaration_type', 'in', ('t1_in',)),
                ], limit=1)
                if t1_file:
                    rec.t1_customs_file_id = t1_file.id
                    if t1_file.state == 'done':
                        rec.status = 'closed'
                        rec.satisfied_date = t1_file.t1_closed_date
        return records