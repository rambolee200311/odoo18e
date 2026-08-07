from odoo import api, fields, models, _


class CarrierSettlementAllocation(models.Model):
    """Allocation of billing line amounts to transport orders."""
    _name = 'tlmp.carrier.settlement.allocation'
    _description = 'Settlement Allocation'
    _rec_name = 'display_name'

    billing_line_id = fields.Many2one(
        'tlmp.carrier.billing.line', string='Billing Line',
        required=True, ondelete='cascade')
    charge_type_id = fields.Many2one(
        'tlmp.carrier.charge.type', string='Charge Type')
    transport_order_id = fields.Many2one(
        'tlmp.transport.order', string='Transport Order',
        required=True)
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='billing_line_id.currency_id', store=False)
    allocated_amount = fields.Monetary(
        string='Allocated Amount', currency_field='currency_id',
        required=True)
    allocation_method = fields.Selection([
        ('manual', 'Manual'),
    ], string='Allocation Method', default='manual')
    batch_line_id = fields.Many2one('tlmp.carrier.settlement.batch.line', string='Batch Line')

    # Sprint31 BUG FIX: reversal fields for correction audit (were dropped by sed)
    is_reversal = fields.Boolean(string='Is Reversal', default=False, readonly=True)
    reversed_allocation_id = fields.Many2one(
        'tlmp.carrier.settlement.allocation', string='Reversed Allocation',
        readonly=True, help='The original allocation that was reversed')
    correction_case_id = fields.Many2one(
        'tlmp.carrier.settlement.case', string='Correction Case',
        readonly=True)
    correction_reason = fields.Text(string='Correction Reason')
    correction_user_id = fields.Many2one(
        'res.users', string='Corrected By', readonly=True)
    correction_date = fields.Datetime(string='Correction Date', readonly=True)
    change_reason = fields.Char(string='Change Reason')

    # Audit trail
    history_ids = fields.One2many(
        'tlmp.carrier.allocation.history', 'allocation_id',
        string='Allocation History')

    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name', store=False)

    _sql_constraints = [
        ('unique_billing_line_order',
         'unique(billing_line_id, transport_order_id)',
         'An allocation for this billing line and order already exists.'),
        ('check_allocated_amount_positive',
         'check(allocated_amount >= 0)',
         'Allocated amount must be non-negative.'),
    ]

    @api.depends('billing_line_id', 'transport_order_id')
    def _compute_display_name(self):
        for r in self:
            bl_ref = r.billing_line_id.document_id.name if r.billing_line_id else ''
            to_ref = r.transport_order_id.name if r.transport_order_id else ''
            r.display_name = '%s/%s' % (bl_ref, to_ref)

    @api.constrains('allocated_amount')
    def _check_allocation_sum(self):
        for r in self:
            if not r.billing_line_id:
                continue
            existing = self.search([
                ('billing_line_id', '=', r.billing_line_id.id),
                ('id', '!=', r.id if r.id else 0),
            ])
            total = sum(existing.mapped('allocated_amount')) + (r.allocated_amount or 0.0)
            line_total = r.billing_line_id.line_total or 0.0
            if total > line_total:
                raise models.ValidationError(_(
                    'Total allocated amount (%.2f) exceeds billing line total (%.2f).',
                    total, line_total))

    def write(self, vals):
        if self._context.get('skip_allocation_audit'):
            return super(CarrierSettlementAllocation, self).write(vals)
        for record in self:
            old_amount = record.allocated_amount
            old_order = record.transport_order_id
            old_charge = record.charge_type_id
            res = super(CarrierSettlementAllocation, record).write(vals)
            new_amount = record.allocated_amount
            new_order = record.transport_order_id
            new_charge = record.charge_type_id
            if (old_amount != new_amount or
                    old_order != new_order or
                    old_charge != new_charge):
                reason = vals.get('change_reason', '')
                self.env['tlmp.carrier.allocation.history'].create({
                    'allocation_id': record.id,
                    'operation_type': 'update',
                    'old_amount': old_amount,
                    'new_amount': new_amount,
                    'old_order_id': old_order.id if old_order else False,
                    'new_order_id': new_order.id if new_order else False,
                    'old_charge_type_id': old_charge.id if old_charge else False,
                    'new_charge_type_id': new_charge.id if new_charge else False,
                    'change_reason': reason,
                    'operator': self.env.uid,
                })
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            reason = record.change_reason or _('Manual allocation')
            self.env['tlmp.carrier.allocation.history'].create({
                'allocation_id': record.id,
                'operation_type': 'create',
                'new_amount': record.allocated_amount,
                'new_order_id': record.transport_order_id.id,
                'new_charge_type_id': record.charge_type_id.id if record.charge_type_id else False,
                'change_reason': reason,
                'operator': self.env.uid,
            })
        return records

    def unlink(self):
        for record in self:
            reason = self.env.context.get('allocation_unlink_reason', '')
            self.env['tlmp.carrier.allocation.history'].create({
                'allocation_id': record.id,
                'operation_type': 'delete',
                'old_amount': record.allocated_amount,
                'old_order_id': record.transport_order_id.id,
                'old_charge_type_id': record.charge_type_id.id if record.charge_type_id else False,
                'change_reason': reason,
                'operator': self.env.uid,
            })
        return super().unlink()


class CarrierAllocationHistory(models.Model):
    """Audit log for allocation changes."""
    _name = 'tlmp.carrier.allocation.history'
    _description = 'Allocation History'
    _order = 'change_date desc'

    allocation_id = fields.Many2one(
        'tlmp.carrier.settlement.allocation', string='Allocation',
        required=True, ondelete='cascade')
    operation_type = fields.Selection([
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('reallocate', 'Reallocate'),
    ], string='Operation Type', required=True)
    old_amount = fields.Monetary(string='Old Amount', currency_field='currency_id')
    new_amount = fields.Monetary(string='New Amount', currency_field='currency_id')
    old_order_id = fields.Many2one('tlmp.transport.order', string='Old Order')
    new_order_id = fields.Many2one('tlmp.transport.order', string='New Order')
    old_charge_type_id = fields.Many2one(
        'tlmp.carrier.charge.type', string='Old Charge Type')
    new_charge_type_id = fields.Many2one(
        'tlmp.carrier.charge.type', string='New Charge Type')
    change_reason = fields.Text(string='Change Reason')
    operator = fields.Many2one('res.users', string='Operator')
    change_date = fields.Datetime(
        string='Change Date', default=fields.Datetime.now)
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='allocation_id.currency_id', store=False)
