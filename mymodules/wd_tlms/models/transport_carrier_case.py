from odoo import api, fields, models, _


class CarrierSettlementCase(models.Model):
    """结算争议工单 — 异常处理与手动修正入口"""
    _name = 'tlmp.carrier.settlement.case'
    _description = 'Settlement Case'
    _rec_name = 'name'
    _order = 'create_date desc'

    name = fields.Char(string='Case No.', required=True, copy=False,
                       default=lambda self: _('New'))
    case_type = fields.Selection([
        ('unmatched', 'Unmatched'),
        ('amount_discrepancy', 'Amount Discrepancy'),
        ('deduction', 'Deduction'),
        ('carrier_dispute', 'Carrier Dispute'),
        ('other', 'Other'),
    ], string='Case Type', required=True)
    source = fields.Selection([
        ('auto_matching', 'Auto Matching'),
        ('manual', 'Manual'),
        ('import', 'Import'),
    ], string='Source', default='auto_matching', required=True)
    state = fields.Selection([
        ('open', 'Open'),
        ('processing', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='open', required=True)
    priority = fields.Selection([
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ], string='Priority', default='normal')
    owner_user_id = fields.Many2one(
        'res.users', string='Owner',
        default=lambda self: self.env.uid)
    line_ids = fields.One2many(
        'tlmp.carrier.settlement.case.line', 'case_id',
        string='Case Lines')
    resolution = fields.Text(string='Resolution')
    resolved_by = fields.Many2one('res.users', string='Resolved By')
    resolved_date = fields.Datetime(string='Resolved Date')
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'tlmp.settlement.case.seq') or _('New')
        return super().create(vals_list)

    def action_open(self):
        self.write({'state': 'open'})

    def action_process(self):
        self.write({'state': 'processing'})

    def action_resolve(self):
        self.write({'state': 'resolved', 'resolved_by': self.env.uid,
                     'resolved_date': fields.Datetime.now()})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reopen(self):
        if self.state == 'closed':
            self.write({'state': 'open'})


class CarrierSettlementCaseLine(models.Model):
    """争议工单明细 — 一个 case 可关联多个 billing.line"""
    _name = 'tlmp.carrier.settlement.case.line'
    _description = 'Settlement Case Line'
    _rec_name = 'display_name'

    case_id = fields.Many2one(
        'tlmp.carrier.settlement.case', string='Case',
        required=True, ondelete='cascade')
    billing_line_id = fields.Many2one(
        'tlmp.carrier.billing.line', string='Billing Line',
        required=True)
    # allocation_ids temporarily removed - will be re-added as Many2many in Sprint36
    issue_amount = fields.Monetary(string='Issue Amount')
    resolution_amount = fields.Monetary(string='Resolution Amount')
    expected_amount = fields.Monetary(
        string='Expected Amount',
        help='创建 billing.line 时的 snapshot')
    variance_amount = fields.Monetary(string='Variance')
    variance_percent = fields.Float(string='Variance %')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='billing_line_id.currency_id')
    note = fields.Text(string='Note')
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name', store=False)

    @api.depends('case_id', 'billing_line_id')
    def _compute_display_name(self):
        for r in self:
            ref = r.billing_line_id.document_id.name if r.billing_line_id else ''
            r.display_name = '%s / %s' % (r.case_id.name or '', ref)
