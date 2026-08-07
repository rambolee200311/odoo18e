from odoo import models, fields, api, _


class PricingRule(models.Model):
    _name = 'tlmp.pricing.rule'
    _description = 'Pricing Rule'

    name = fields.Char(string='Name', required=True)
    rule_type = fields.Selection([
        ('container', 'Container'),
        ('weight', 'Weight'),
        ('volume', 'Volume'),
        ('package', 'Package'),
        ('flat', 'Flat Rate'),
    ], string='Rule Type', required=True)
    carrier_type = fields.Selection([
        ('own_fleet', 'Own Fleet'),
        ('contracted', 'Contracted'),
        ('subcontracted', 'Subcontracted'),
    ], string='Carrier Type')
    transport_type_id = fields.Many2one('tlmp.transport.type',
        string='Transport Type', required=False,
        help='Leave empty to match all transport types.')
    carrier_id = fields.Many2one('res.partner', string='Carrier')
    date_from = fields.Date(string='Valid From')
    date_to = fields.Date(string='Valid To')
    priority = fields.Integer(string='Priority', default=10)
    line_ids = fields.One2many('tlmp.pricing.rule.line', 'rule_id', string='Tiers')
    active = fields.Boolean(default=True)


class PricingRuleLine(models.Model):
    _name = 'tlmp.pricing.rule.line'
    _description = 'Pricing Rule Tier'

    rule_id = fields.Many2one('tlmp.pricing.rule', string='Rule', required=True, ondelete='cascade')
    min_value = fields.Float(string='Min')
    max_value = fields.Float(string='Max')
    unit_price = fields.Monetary(string='Unit Price')
    base_fee = fields.Monetary(string='Base Fee')
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.company.currency_id)


class ContainerPricelist(models.Model):
    _name = 'tlmp.container.pricelist'
    _description = 'Container Pricelist'

    name = fields.Char(string='Name')
    carrier_id = fields.Many2one('res.partner', string='Carrier')
    container_type = fields.Selection([
        ('20GP', '20GP'), ('40GP', '40GP'), ('40HQ', '40HQ'), ('45HQ', '45HQ'),
    ], string='Container Type')
    route_from = fields.Char(string='From')
    route_to = fields.Char(string='To')
    price = fields.Monetary(string='Price')
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.company.currency_id)
    valid_from = fields.Date(string='Valid From')
    valid_to = fields.Date(string='Valid To')
