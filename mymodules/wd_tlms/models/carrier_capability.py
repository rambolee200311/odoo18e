from odoo import models, fields


class CarrierCapability(models.Model):
    _name = 'tlmp.carrier.capability'
    _description = 'Carrier Capability'
    _rec_name = 'name'

    code = fields.Char(string='Code', required=True)
    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')
    active = fields.Boolean(string='Active', default=True)
