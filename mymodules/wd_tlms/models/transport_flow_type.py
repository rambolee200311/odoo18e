from odoo import fields, models, _

class TransportFlowType(models.Model):
    _name = 'tlmp.transport.flow.type'
    _description = 'Transport Flow Type'
    _rec_name = 'name'
    _order = 'code'

    code = fields.Char(string='Code', required=True)
    name = fields.Char(string='Name', required=True, translate=True)
    active = fields.Boolean(string='Active', default=True)

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Flow type code must be unique.'),
    ]
