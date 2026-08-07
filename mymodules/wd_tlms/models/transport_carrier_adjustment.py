from odoo import api, fields, models, _


class CarrierSettlementAdjustment(models.Model):
    """结算调整单 — 替代 Credit/Debit 扩展 billing.document
    独立建模，预留 account_move_id 为未来 Sprint33 自动记账。
    """
    _name = 'tlmp.carrier.settlement.adjustment'
    _description = 'Settlement Adjustment'
    _rec_name = 'name'
    _order = 'create_date desc'

    name = fields.Char(string='Adjustment No.', required=True, copy=False,
                       default=lambda self: _('New'))
    type = fields.Selection([
        ('carrier_credit', 'Carrier Credit — Reduce Payable'),
        ('carrier_debit', 'Carrier Debit — Increase Payable'),
    ], string='Adjustment Type', required=True)
    source_case_id = fields.Many2one(
        'tlmp.carrier.settlement.case', string='Source Case')
    batch_id = fields.Many2one(
        'tlmp.carrier.settlement.batch', string='Batch')
    carrier_partner_id = fields.Many2one(
        'res.partner', string='Carrier', required=True,
        domain="[('is_company', '=', True)]")
    original_document_id = fields.Many2one(
        'tlmp.carrier.billing.document', string='Original Document')
    amount = fields.Monetary(string='Amount', required=True)
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id)
    reason = fields.Text(string='Reason')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft')
    # Approval audit
    created_by = fields.Many2one('res.users', string='Created By',
                                 default=lambda self: self.env.uid, readonly=True)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True)
    approved_date = fields.Datetime(string='Approved Date', readonly=True)
    cancel_reason = fields.Text(string='Cancel Reason')
    cancelled_by = fields.Many2one('res.users', string='Cancelled By', readonly=True)
    cancelled_date = fields.Datetime(string='Cancelled Date', readonly=True)
    # Future account.move integration
    account_move_id = fields.Many2one(
        'account.move', string='Journal Entry', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'tlmp.adjustment.seq') or _('New')
        return super().create(vals_list)

    def action_approve(self):
        self.write({
            'state': 'approved',
            'approved_by': self.env.uid,
            'approved_date': fields.Datetime.now(),
        })

    def action_cancel(self):
        self.write({
            'state': 'cancelled',
            'cancelled_by': self.env.uid,
            'cancelled_date': fields.Datetime.now(),
        })


class CarrierSettlementBatchApprovalHistory(models.Model):
    """Batch 审批历史 — 记录审批事件链"""
    _name = 'tlmp.carrier.settlement.batch.approval.history'
    _description = 'Batch Approval History'
    _order = 'date desc'

    batch_id = fields.Many2one(
        'tlmp.carrier.settlement.batch', string='Batch',
        required=True, ondelete='cascade')
    action = fields.Selection([
        ('submit', 'Submit'),
        ('approve', 'Approve'),
        ('reject', 'Reject'),
    ], string='Action', required=True)
    user = fields.Many2one('res.users', string='User', required=True)
    date = fields.Datetime(string='Date', default=fields.Datetime.now)
    note = fields.Text(string='Note')
