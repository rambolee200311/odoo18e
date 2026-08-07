from odoo import models, fields, api, _


class CustomerBill(models.Model):
    _name = 'tlmp.customer.bill'
    _description = 'Customer Bill'
    _rec_name = 'name'

    name = fields.Char(string='Bill No.', required=True, copy=False,
                       default=lambda self: _('New'))
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    order_ids = fields.Many2many('tlmp.transport.order', string='Orders')
    bill_date = fields.Date(string='Bill Date', default=fields.Date.today())
    due_date = fields.Date(string='Due Date')
    line_ids = fields.One2many('tlmp.customer.bill.line', 'bill_id', string='Lines')
    total_amount = fields.Monetary(string='Total', compute='_compute_total', store=True)
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.company.currency_id)
    account_move_id = fields.Many2one('account.move', string='Invoice', readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'), ('confirmed', 'Confirmed'),
        ('posted', 'Posted'), ('paid', 'Paid'), ('cancelled', 'Cancelled'),
    ], string='Status', default='draft')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('tlmp.bill.seq') or _('New')
        return super().create(vals_list)

    @api.depends('line_ids.subtotal')
    def _compute_total(self):
        for r in self:
            r.total_amount = sum(r.line_ids.mapped('subtotal'))


class CustomerBillLine(models.Model):
    _name = 'tlmp.customer.bill.line'
    _description = 'Bill Line'

    bill_id = fields.Many2one('tlmp.customer.bill', string='Bill', required=True, ondelete='cascade')
    order_id = fields.Many2one('tlmp.transport.order', string='Order')
    description = fields.Char(string='Description')
    quantity = fields.Float(string='Qty', default=1.0)
    unit_price = fields.Monetary(string='Unit Price')
    subtotal = fields.Monetary(string='Subtotal', compute='_compute_subtotal', store=True)
    currency_id = fields.Many2one('res.currency', related='bill_id.currency_id')

    @api.depends('quantity', 'unit_price')
    def _compute_subtotal(self):
        for r in self:
            r.subtotal = (r.unit_price or 0.0) * r.quantity
