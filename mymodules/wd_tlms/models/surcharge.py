from odoo import models, fields, api, _


class SurchargeType(models.Model):
    _name = 'tlmp.surcharge.type'
    _description = 'Surcharge Type'

    name = fields.Char(string='Name', required=True, translate=True)
    code = fields.Char(string='Code', required=True)
    default_amount = fields.Monetary(string='Default Amount')
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.company.currency_id)
    active = fields.Boolean(default=True)


class Surcharge(models.Model):
    _name = 'tlmp.surcharge'
    _description = 'Surcharge'

    surcharge_type_id = fields.Many2one('tlmp.surcharge.type', string='Type', required=True)
    order_id = fields.Many2one('tlmp.transport.order', string='Order', required=True)
    container_id = fields.Many2one('tlmp.transport.container', string='Container')
    description = fields.Text(string='Description')
    quantity = fields.Float(string='Qty', default=1.0)
    unit_price = fields.Monetary(string='Unit Price', required=True)
    amount = fields.Monetary(string='Amount', compute='_compute_amount', store=True)
    billing_party = fields.Selection([
        ('customer', 'Customer'), ('us', 'Our Company'), ('carrier', 'Carrier'),
    ], string='Billing Party', required=True, default='customer')
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.company.currency_id)

    @api.depends('quantity', 'unit_price')
    def _compute_amount(self):
        for r in self:
            r.amount = (r.unit_price or 0.0) * r.quantity
