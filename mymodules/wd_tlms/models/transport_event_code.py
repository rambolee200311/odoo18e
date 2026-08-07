# -*- coding: utf-8 -*-
from odoo import fields, models, _


class TransportEventCode(models.Model):
    """Versioned event code dictionary (Sprint50-B)."""

    _name = 'tlmp.transport.event.code'
    _description = 'Transport Event Code'
    _order = 'category, code, id'
    _rec_name = 'code'

    code = fields.Char(string='Code', required=True, index=True)
    name = fields.Char(string='Name', required=True)
    category = fields.Selection([
        ('business', 'Business'),
        ('state', 'State'),
        ('integration', 'Integration'),
    ], string='Category', required=True, default='state')
    version = fields.Char(string='Version', default='1.0')
    active = fields.Boolean(string='Active', default=True)
    deprecated_at = fields.Datetime(string='Deprecated At')

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code, version)',
         _('Event code + version must be unique.')),
    ]
