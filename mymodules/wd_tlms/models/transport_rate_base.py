from odoo import models, fields, api, _


class RateBase(models.Model):
    _name = 'transport.rate.base'
    _description = 'Rate Base'
    _order = 'name'
    _rec_name = 'name'

    name = fields.Char(string='Rate Name', required=True, index=True)
    fee_type_id = fields.Many2one('world.depot.charge.item', string='Fee Type', required=True)
    transport_type_id = fields.Many2one('tlmp.transport.type',
        string='Transport Type', required=False,
        help='Set to a specific type, or leave empty for all types.')
    rate_type = fields.Selection([
        ('fixed', 'Fixed Amount'),
        ('per_km', 'Per Kilometer'),
        ('per_kg', 'Per KG'),
        ('per_container', 'Per Container'),
        ('per_pallet', 'Per Pallet'),
        ('percentage', 'Percentage'),
    ], string='Rate Type', default='fixed', required=True)
    amount = fields.Monetary(string='Rate Amount', required=True, default=0.0)
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id)
    valid_from = fields.Date(string='Valid From')
    valid_to = fields.Date(string='Valid To')
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)
    active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')
