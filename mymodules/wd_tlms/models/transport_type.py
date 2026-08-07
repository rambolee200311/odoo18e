# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class TransportType(models.Model):
    _name = 'tlmp.transport.type'
    _description = 'Transport Type - Master Data'
    _rec_name = 'name'
    _order = 'sequence, id'

    code = fields.Char(string='Code', required=True, index=True)
    name = fields.Char(string='Name', required=True, translate=True)
    category = fields.Selection([
        ('ftl', 'FTL'),
        ('ltl', 'LTL'),
        ('parcel', 'Parcel'),
        ('return', 'Return'),
    ], string='Category', required=True,
       help='Business classification: FTL / LTL / Parcel / Return')
    mode = fields.Selection([
        ('road', 'Road'),
        ('air', 'Air'),
        ('sea', 'Sea'),
        ('rail', 'Rail'),
    ], string='Mode', required=True, default='road',
       help='Transport mode: Road / Air / Sea / Rail')
    description = fields.Text(string='Description')
    sequence = fields.Integer(string='Sequence', default=10)
    is_active = fields.Boolean(string='Active', default=True)

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', _('Type code must be unique!')),
    ]

    def name_get(self):
        result = []
        for r in self:
            label = '%s [%s]' % (r.name, r.code) if r.code else r.name
            result.append((r.id, label))
        return result

    @api.model
    def _get_by_code(self, code):
        """Lookup transport type by code. Returns browse record or None."""
        return self.search([('code', '=', code)], limit=1)

    @api.model
    def _type_map(self):
        """Return dict mapping code to id for type_map lookups. Used by pickup_plan, container_service."""
        return {t.code: t.id for t in self.search([])}
