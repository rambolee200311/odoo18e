from odoo import api, fields, models, _


class CarrierBillingDocument(models.Model):
    """Carrier billing document - source of truth for carrier settlement."""
    _name = 'tlmp.carrier.billing.document'
    _description = 'Carrier Billing Document'
    _rec_name = 'name'
    _order = 'create_date desc'

    name = fields.Char(string='Document No.', required=True, copy=False,
                       default=lambda self: _('New'))
    carrier_id = fields.Many2one(
        'res.partner', string='Carrier', required=True,
        domain="[('is_company', '=', True)]")

    # ── External Invoice Reference (for Import Idempotency) ──
    external_invoice_no = fields.Char(
        string='External Invoice No', index=True,
        help='Carrier original invoice number. Part of business_idempotency_key.')
    invoice_version = fields.Char(
        string='Invoice Version', index=True,
        help='Invoice version for supersede tracking.')
    external_document_ref = fields.Char(string='External Document Ref')
    idempotency_hash = fields.Char(
        string='Idempotency Hash', index=True,
        help='SHA256(carrier + invoice_no + version + checksum). Prevents duplicate import.')
    file_checksum = fields.Char(string='File Checksum',
                                help='SHA256 of original upload file.')

    # ── Import Context (billing must come through Intake Layer) ──
    import_batch_id = fields.Many2one(
        'tlmp.carrier.invoice.import', string='Import Batch',
        readonly=True, ondelete='restrict')
    import_line_id = fields.Many2one(
        'tlmp.carrier.invoice.import.line', string='Import Line',
        readonly=True, ondelete='restrict')
    document_no = fields.Char(string='Original Document No.',
                              help='Carrier original invoice/statement number.')
    document_type = fields.Selection([
        ('invoice', 'Invoice'),
        ('statement', 'Statement'),
        ('debit_note', 'Debit Note'),
        ('credit_note', 'Credit Note'),
        ('cost_sheet', 'Cost Sheet'),
    ], string='Document Type', default='invoice')
    billing_period_start = fields.Date(string='Period Start')
    billing_period_end = fields.Date(string='Period End')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)
    carrier_service_id = fields.Many2one(
        'tlmp.carrier.service', string='Carrier Service')
    transport_mode = fields.Selection([
        ('truck', 'Truck (FTL/LTL)'),
        ('express', 'Express (Parcel)'),
        ('_3pl', '3PL (Groupage)'),
    ], string='Transport Mode', default='truck')

    # Amounts
    total_amount = fields.Monetary(
        string='Total Amount', currency_field='currency_id',
        compute='_compute_total_amount', store=True)
    amount_sign = fields.Selection([
        ('positive', 'Positive (Debit)'),
        ('negative', 'Negative (Credit)'),
    ], string='Amount Sign', default='positive')

    # State machine (extended: Draft -> Active -> Superseded | Cancelled)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('active', 'Active'),
        ('superseded', 'Superseded'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True)
    confirmed_by = fields.Many2one(
        'res.users', string='Confirmed By', readonly=True)
    confirmed_date = fields.Datetime(string='Confirmed Date', readonly=True)
    cancel_reason = fields.Text(string='Cancel Reason')

    # Lines & link to old settlement
    line_ids = fields.One2many(
        'tlmp.carrier.billing.line', 'document_id',
        string='Billing Lines', copy=False)
    legacy_settlement_id = fields.Many2one(
        'tlmp.carrier.settlement', string='Legacy Settlement',
        help='Reference to the old carrier.settlement model. Not bidirectional.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'tlmp.billing.document.seq') or _('New')
        return super().create(vals_list)

    @api.depends('line_ids.line_total')
    def _compute_total_amount(self):
        for r in self:
            r.total_amount = sum(r.line_ids.mapped('line_total'))

    def action_confirm(self):
        self.write({
            'state': 'active',
            'confirmed_by': self.env.uid,
            'confirmed_date': fields.Datetime.now(),
        })

    def action_supersede(self):
        self.write({'state': 'superseded'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})


class CarrierBillingLine(models.Model):
    """Individual line on a carrier billing document."""
    _name = 'tlmp.carrier.billing.line'
    _description = 'Carrier Billing Line'
    _order = 'document_id, id'

    document_id = fields.Many2one(
        'tlmp.carrier.billing.document', string='Billing Document',
        required=True, ondelete='cascade')
    service_date = fields.Date(string='Service Date')
    raw_description = fields.Text(string='Description')
    carrier_reference = fields.Char(
        string='Carrier Reference',
        help='Carrier shipment/waybill/tracking number.')
    raw_reference = fields.Char(
        string='Raw Reference',
        help='Original reference text from the carrier bill.')
    external_line_key = fields.Char(
        string='External Line Key', index=True,
        help='Unique key within document for idempotency.')
    charge_type_id = fields.Many2one(
        'tlmp.carrier.charge.type', string='Charge Type')
    net_amount = fields.Monetary(string='Net Amount', currency_field='currency_id')
    tax = fields.Monetary(string='Tax', currency_field='currency_id')
    line_total = fields.Monetary(
        string='Line Total', currency_field='currency_id',
        compute='_compute_line_total', store=True)
    amount_sign = fields.Selection([
        ('positive', 'Positive (Debit)'),
        ('negative', 'Negative (Credit)'),
    ], string='Amount Sign', default='positive', required=True)

    # Currency inherited from document
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='document_id.currency_id', store=False)

    # Quick match field
    transport_order_id = fields.Many2one(
        'tlmp.transport.order', string='Transport Order',
        help='Quick manual match to a transport order.')

    # Allocations
    is_auto_matched = fields.Boolean(string='Auto Matched', default=False)
    batch_line_id = fields.Many2one('tlmp.carrier.settlement.batch.line', string='Batch Line')
    allocation_ids = fields.One2many(
        'tlmp.carrier.settlement.allocation', 'billing_line_id',
        string='Allocations')
    allocated_total = fields.Monetary(
        string='Allocated Total', currency_field='currency_id',
        compute='_compute_allocated_total', store=False)
    remaining_amount = fields.Monetary(
        string='Remaining', currency_field='currency_id',
        compute='_compute_remaining', store=False)

    @api.depends('net_amount', 'tax', 'amount_sign')
    def _compute_line_total(self):
        for r in self:
            base = (r.net_amount or 0.0) + (r.tax or 0.0)
            if r.amount_sign == 'negative':
                r.line_total = -base
            else:
                r.line_total = base

    @api.depends('line_total', 'expected_amount')
    def _compute_variance(self):
        for r in self:
            expected = r.expected_amount or 0.0
            actual = r.line_total or 0.0
            r.variance_amount = actual - expected
            r.variance_percent = ((actual - expected) / expected * 100) if expected else 0.0

    @api.depends('allocation_ids.allocated_amount')
    def _compute_allocated_total(self):
        for r in self:
            r.allocated_total = sum(r.allocation_ids.mapped('allocated_amount'))

    @api.depends('line_total', 'allocated_total')
    def _compute_remaining(self):
        for r in self:
            r.remaining_amount = (r.line_total or 0.0) - (r.allocated_total or 0.0)
