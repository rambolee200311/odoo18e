from odoo import api, fields, models, _


class CarrierSettlementBatch(models.Model):
    """月度结算批次 — 含 batch.line 结算快照"""
    _name = 'tlmp.carrier.settlement.batch'
    _description = 'Settlement Batch'
    _rec_name = 'name'
    _order = 'create_date desc'

    name = fields.Char(string='Batch No.', required=True, copy=False,
                       default=lambda self: _('New'))
    carrier_partner_id = fields.Many2one(
        'res.partner', string='Carrier',
        domain="[('is_company', '=', True)]", required=True)
    period_start = fields.Date(string='Period Start', required=True)
    period_end = fields.Date(string='Period End', required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('processing', 'Processing'),
        ('approved', 'Approved'),
        ('closed', 'Closed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True)
    line_ids = fields.One2many(
        'tlmp.carrier.settlement.batch.line', 'batch_id',
        string='Batch Lines')
    aggregated_total = fields.Monetary(
        string='Aggregated Total',
        currency_field='currency_id',
        compute='_compute_total', store=True)
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)
    confirmed_by = fields.Many2one('res.users', string='Confirmed By', readonly=True)
    confirmed_date = fields.Datetime(string='Confirmed Date', readonly=True)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True)
    approved_date = fields.Datetime(string='Approved Date', readonly=True)
    reject_reason = fields.Text(string='Reject Reason')
    approval_history_ids = fields.One2many(
        'tlmp.carrier.settlement.batch.approval.history', 'batch_id',
        string='Approval History')
    note = fields.Text(string='Note')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'tlmp.batch.seq') or _('New')
        return super().create(vals_list)

    @api.depends('line_ids.snapshot_amount')
    def _compute_total(self):
        for r in self:
            r.aggregated_total = sum(r.line_ids.mapped('snapshot_amount'))

    def action_confirm(self):
        self.write({'state': 'confirmed', 'confirmed_by': self.env.uid,
                    'confirmed_date': fields.Datetime.now()})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_submit(self):
        self.write({'state': 'submitted'})
        self.env['tlmp.carrier.settlement.batch.approval.history'].create({
            'batch_id': self.id, 'action': 'submit', 'user': self.env.uid})

    def action_approve(self):
        self.write({'state': 'approved', 'approved_by': self.env.uid,
                     'approved_date': fields.Datetime.now()})
        self.env['tlmp.carrier.settlement.batch.approval.history'].create({
            'batch_id': self.id, 'action': 'approve', 'user': self.env.uid})

    def action_reject(self):
        self.write({'state': 'rejected'})
        self.env['tlmp.carrier.settlement.batch.approval.history'].create({
            'batch_id': self.id, 'action': 'reject', 'user': self.env.uid})

    def action_cancel(self):
        self.write({'state': 'cancelled'})


class CarrierSettlementBatchLine(models.Model):
    """结算批次明细 — snapshot 快照"""
    _name = 'tlmp.carrier.settlement.batch.line'
    _description = 'Settlement Batch Line'
    _rec_name = 'display_name'

    batch_id = fields.Many2one(
        'tlmp.carrier.settlement.batch', string='Batch',
        required=True, ondelete='cascade')
    billing_document_id = fields.Many2one(
        'tlmp.carrier.billing.document', string='Billing Document')
    billing_line_id = fields.Many2one(
        'tlmp.carrier.billing.line', string='Billing Line')
    allocation_ids = fields.One2many(
        'tlmp.carrier.settlement.allocation', 'batch_line_id',
        string='Allocations')
    snapshot_amount = fields.Monetary(
        string='Snapshot Amount',
        currency_field='snapshot_currency_id',
        help='结算快照金额，防止后续修改影响历史批次')
    snapshot_currency_id = fields.Many2one(
        'res.currency', string='Snapshot Currency')
    created_date = fields.Datetime(
        string='Created', default=fields.Datetime.now)

    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name', store=False)

    @api.depends('batch_id', 'billing_line_id')
    def _compute_display_name(self):
        for r in self:
            ref = r.billing_line_id.document_id.name if r.billing_line_id else ''
            r.display_name = '%s / %s' % (r.batch_id.name or '', ref)
