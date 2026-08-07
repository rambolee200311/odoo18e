# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class TransportUnDictionary(models.Model):
    _name = 'tlmp.transport.un.dictionary'
    _description = 'UN Dictionary - ADR Dangerous Goods Reference'
    _rec_name = 'display_name'
    _order = 'un_number'

    un_number = fields.Char(string='UN Number', required=True, index=True)
    proper_shipping_name = fields.Char(string='Proper Shipping Name', required=True)
    hazard_class = fields.Char(string='Class', required=True)
    classification_code = fields.Char(string='Classification Code')
    packing_group = fields.Selection([
        ('I', 'I'),
        ('II', 'II'),
        ('III', 'III'),
        ('none', 'N/A'),
    ], string='Packing Group', default='none')
    tunnel_code = fields.Char(string='Tunnel Code')
    transport_category = fields.Char(string='Transport Category')
    special_provision = fields.Char(string='Special Provision')
    is_active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')

    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)

    @api.depends('un_number', 'proper_shipping_name')
    def _compute_display_name(self):
        for r in self:
            r.display_name = '%s - %s' % (r.un_number, r.proper_shipping_name)

    _sql_constraints = [
        ('un_number_unique', 'UNIQUE(un_number)',
         _('UN number must be unique!')),
    ]

    @api.constrains('hazard_class')
    def _check_hazard_class(self):
        for r in self:
            if r.hazard_class and not r.hazard_class.replace('.', '').isdigit():
                raise ValidationError(_('Hazard class must be a numeric value (e.g. 1, 2.1, 3).'))

    @api.constrains('un_number')
    def _check_un_number(self):
        for r in self:
            if r.un_number and not r.un_number.startswith('UN'):
                raise ValidationError(_('UN number must start with UN (e.g. UN1203).'))

    def name_get(self):
        result = []
        for r in self:
            result.append((r.id, '%s - %s' % (r.un_number, r.proper_shipping_name)))
        return result
