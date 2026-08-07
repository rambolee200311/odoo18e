from odoo import api, fields, models, _


class CarrierAllocationService(models.AbstractModel):
    """Allocation Service — 隔离 UI 与 allocation 直接交互。
    用于：人工确认匹配、batch settlement、dispute resolution 复用。
    """
    _name = 'tlmp.carrier.allocation.service'
    _description = 'Carrier Allocation Service'

    @api.model
    def create_allocation_from_suggestion(self, suggestion):
        """Create settlement allocation from confirmed suggestion."""
        suggestion.ensure_one()
        if suggestion.state != 'confirmed':
            raise models.ValidationError(_(
                'Only confirmed suggestions can create allocations.'))

        billing_line = suggestion.billing_line_id
        if not billing_line:
            raise models.ValidationError(_('Billing line is required.'))

        order = suggestion.candidate_order_id
        if not order:
            raise models.ValidationError(_('Candidate transport order is required.'))

        alloc = self.env['tlmp.carrier.settlement.allocation'].create({
            'billing_line_id': billing_line.id,
            'charge_type_id': billing_line.charge_type_id.id,
            'transport_order_id': order.id,
            'allocated_amount': billing_line.remaining_amount,
            'allocation_method': 'manual',
            'change_reason': _('Match suggestion confirmed'),
        })

        self.env['tlmp.carrier.matching.history'].create({
            'billing_line_id': billing_line.id,
            'transport_order_id': order.id,
            'suggestion_id': suggestion.id,
            'operation': 'allocation_created',
            'from_state': 'confirmed',
            'to_state': 'confirmed',
            'operator': self.env.uid,
        })
        return alloc

    @api.model
    def reverse_allocation(self, allocation, reason=''):
        """Reverse a settlement allocation (mark as reversed in history)."""
        allocation.ensure_one()
        self.env['tlmp.carrier.matching.history'].create({
            'billing_line_id': allocation.billing_line_id.id,
            'transport_order_id': allocation.transport_order_id.id,
            'operation': 'allocation_reversed',
            'from_state': 'confirmed',
            'to_state': 'draft',
            'operator': self.env.uid,
            'note': reason,
        })
        allocation.unlink()
        return True
