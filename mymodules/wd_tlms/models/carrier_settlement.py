from odoo import models, fields, api, _


class CarrierSettlement(models.Model):
    _name = 'tlmp.carrier.settlement'
    _description = 'Carrier Settlement'
    _rec_name = 'name'

    name = fields.Char(string='Settlement No.', required=True, copy=False,
                       default=lambda self: _('New'))
    carrier_type = fields.Selection([
        ('own_fleet', 'Own Fleet'),
        ('contracted', 'Contracted'),
        ('subcontracted', 'Subcontracted'),
    ], string='Carrier Type', required=True)
    partner_id = fields.Many2one('res.partner', string='Carrier', required=True)
    order_ids = fields.Many2many('tlmp.transport.order', string='Orders')
    line_ids = fields.One2many('tlmp.carrier.settlement.line', 'settlement_id', string='Lines')
    total_amount = fields.Monetary(string='Total', compute='_compute_total', store=True)
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.company.currency_id)
    account_move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True)
    billing_document_id = fields.Many2one(
        'tlmp.carrier.billing.document', string='Billing Document',
        help='Reference to the new billing document model.')
    billing_document_ids = fields.One2many(
        'tlmp.carrier.billing.document', 'legacy_settlement_id',
        string='Billing Documents',
        help='New billing documents linked to this legacy settlement.')
    state = fields.Selection([
        ('draft', 'Draft'), ('confirmed', 'Confirmed'),
        ('posted', 'Posted'), ('paid', 'Paid'), ('cancelled', 'Cancelled'),
    ], string='Status', default='draft')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('tlmp.settlement.seq') or _('New')
        return super().create(vals_list)

    @api.depends('line_ids.amount')
    def _compute_total(self):
        for r in self:
            r.total_amount = sum(r.line_ids.mapped('amount'))


class CarrierSettlementLine(models.Model):
    _name = 'tlmp.carrier.settlement.line'
    _description = 'Settlement Line'

    settlement_id = fields.Many2one('tlmp.carrier.settlement', string='Settlement',
                                    required=True, ondelete='cascade')
    order_id = fields.Many2one('tlmp.transport.order', string='Order')
    description = fields.Char(string='Description')
    amount = fields.Monetary(string='Amount')
    currency_id = fields.Many2one('res.currency', related='settlement_id.currency_id')
