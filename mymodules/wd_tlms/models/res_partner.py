from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_carrier = fields.Boolean(string='Is Carrier')
    is_consignee = fields.Boolean(string='Is Consignee')
    carrier_type = fields.Selection([
        ('own_fleet', 'Own Fleet'),
        ('contracted', 'Contracted'),
        ('subcontracted', 'Subcontracted'),
    ], string='Carrier Type')
    carrier_capability_ids = fields.Many2many(
        'tlmp.carrier.capability', string='Carrier Capabilities')
