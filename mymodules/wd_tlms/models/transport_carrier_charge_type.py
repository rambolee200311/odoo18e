# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class CarrierChargeType(models.Model):
    """Carrier charge type dictionary - fee classification for settlement."""
    _name = 'tlmp.carrier.charge.type'
    _description = 'Carrier Charge Type'
    _rec_name = 'name'
    _order = 'main_category, code'

    code = fields.Char(string='Code', required=True, copy=False)
    name = fields.Char(string='Name', required=True, translate=True)
    main_category = fields.Selection([
        ('freight', 'Freight'),
        ('surcharge', 'Surcharge'),
        ('accessorial', 'Accessorial'),
        ('tax', 'Tax'),
        ('adjustment', 'Adjustment'),
        ('penalty', 'Penalty'),
    ], string='Main Category', required=True, default='freight')
    sub_category = fields.Char(string='Sub Category')
    is_active = fields.Boolean(string='Active', default=True)
    sequence = fields.Integer(string='Sequence', default=10)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)

    _sql_constraints = [
        ('code_unique', 'unique(code, company_id)',
         'Charge type code must be unique per company.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['code'] = vals.get('code', '').upper().replace(' ', '_')
        return super().create(vals_list)
