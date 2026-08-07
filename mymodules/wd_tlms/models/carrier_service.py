# -*- coding: utf-8 -*-
from odoo import models, fields, _


class CarrierService(models.Model):
    _name = 'tlmp.carrier.service'
    _description = 'Carrier Service - Capability Base'
    _rec_name = 'name'
    _order = 'sequence, id'

    code = fields.Char(string='Code', required=True, index=True)
    name = fields.Char(string='Name', required=True, translate=True)
    carrier_id = fields.Many2one(
        'res.partner', string='Carrier Company',
        domain=[('is_company', '=', True)],
        help='The carrier company providing this service (e.g. DHL, UPS, DPD)')
    service_type = fields.Selection([
        ('parcel', 'Parcel'),
        ('express', 'Express'),
        ('freight', 'Freight'),
        ('road', 'Road'),
    ], string='Service Type', required=True, default='parcel',
       help='Parcel / Express / Freight / Road')
    transport_type_ids = fields.Many2many(
        'tlmp.transport.type', string='Applicable Transport Types',
        help='Which transport types this service supports (e.g. Parcel + Return)')
    tracking_url_template = fields.Char(
        string='Tracking URL Template',
        help='URL with {tracking_number} placeholder for carrier tracking page')
    sequence = fields.Integer(string='Sequence', default=10)
    is_active = fields.Boolean(string='Active', default=True)
    description = fields.Text(string='Description')

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', _('Service code must be unique!')),
    ]
