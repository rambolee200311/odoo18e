from odoo import fields, models, _

class TransportDestinationType(models.Model):
    _name = 'tlmp.transport.destination.type'
    _description = 'Transport Destination Type'
    _rec_name = 'name'
    _order = 'code'

    code = fields.Char(string='Code', required=True)
    name = fields.Char(string='Name', required=True, translate=True)
    active = fields.Boolean(string='Active', default=True)

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Destination code must be unique.'),
    ]
