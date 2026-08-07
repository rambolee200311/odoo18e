from odoo import models, fields, api, _
from odoo.exceptions import UserError


class FeeLine(models.Model):
    _name = 'transport.fee.line'
    _description = 'Fee Line'
    _order = 'id'

    # ---- Fee Type (global master data from worlddepot) ----
    fee_type_id = fields.Many2one(
        'world.depot.charge.item', string='Fee Type', required=True,
        help='Global fee type master data from world.depot.charge.item.')

    rate_base_id = fields.Many2one(
        'transport.rate.base', string='Rate Base',
        help='Optional reference to the rate used to calculate this fee.')

    # ---- Dual Direction: Customer Charge (应收) vs Carrier Cost (应付) ----
    party_type = fields.Selection([
        ('customer_charge', 'Customer Charge (应收)'),
        ('carrier_cost', 'Carrier Cost (应付)'),
    ], string='Direction', required=True, default='customer_charge',
        help='customer_charge = charge to customer (income). carrier_cost = cost paid to carrier (expense).')

    partner_id = fields.Many2one(
        'res.partner', string='Counterparty',
        help='The customer (for customer_charge) or carrier (for carrier_cost).')

    # ---- Source traceability ----
    source_type = fields.Selection([
        ('commercial', 'Commercial'),
        ('plan_driven', 'Plan-Driven'),
    ], string='Source Type', required=True, default='commercial',
        help='Identifies which business flow this fee belongs to.')
    source_quote_id = fields.Many2one(
        'tlmp.transport.quote', string='Source Quote',
        index=True, ondelete='cascade',
        help='Quote this fee belongs to (commercial flow).')
    source_order_id = fields.Many2one(
        'tlmp.transport.order', string='Source Order',
        index=True, ondelete='cascade',
        help='Order this fee belongs to (plan-driven or final order).')

    # ---- Quantity & Amount ----
    quantity = fields.Float(string='Quantity', default=1.0)
    unit_amount = fields.Monetary(string='Unit Amount', default=0.0)
    total_amount = fields.Monetary(
        string='Total Amount',
        compute='_compute_total_amount', store=True)
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id)

    description = fields.Text(string='Description')
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)

    @api.depends('quantity', 'unit_amount')
    def _compute_total_amount(self):
        for r in self:
            r.total_amount = (r.quantity or 0.0) * (r.unit_amount or 0.0)

    @api.ondelete(at_uninstall=False)
    def _check_quote_fee_line_not_locked(self):
        for line in self:
            if line.source_quote_id and line.source_quote_id.state != 'draft':
                raise UserError(
                    _('Fee lines of a sent or accepted quote cannot be deleted.'))

    def write(self, vals):
        for line in self:
            if line.source_quote_id and line.source_quote_id.state != 'draft':
                raise UserError(
                    _('Fee lines of a sent or accepted quote cannot be modified.'))
        return super().write(vals)
