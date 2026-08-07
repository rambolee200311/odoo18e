from odoo import api, fields, models, _


class AllocationCorrectionService(models.AbstractModel):
    """手动修正服务 — reverse + replacement 模式
    原 allocation 永久保留，不允许 update/delete。
    """
    _name = 'tlmp.carrier.allocation.correction'
    _description = 'Allocation Correction Service'

    @api.model
    def reverse_allocation(self, allocation, reason='', case_id=False):
        """Reverse an allocation: mark as reversal, create replacement."""
        allocation.ensure_one()
        if allocation.is_reversal:
            raise models.ValidationError(_('Cannot reverse a reversal allocation.'))

        # Check batch protection
        if allocation.batch_line_id and allocation.batch_line_id.batch_id.state in ('closed',):
            raise models.ValidationError(_(
                'Cannot correct allocation in a closed batch.'))

        replaced_amount = allocation.allocated_amount

        # Mark original as reversal
        allocation.write({
            'is_reversal': True,
            'correction_reason': reason,
            'correction_user_id': self.env.uid,
            'correction_date': fields.Datetime.now(),
        })

        # Create replacement allocation
        replacement = self.env['tlmp.carrier.settlement.allocation'].create({
            'billing_line_id': allocation.billing_line_id.id,
            'charge_type_id': allocation.charge_type_id.id,
            'transport_order_id': allocation.transport_order_id.id,
            'allocated_amount': 0.0,
            'allocation_method': 'manual',
            'correction_case_id': case_id or False,
            'reversed_allocation_id': allocation.id,
            'correction_reason': reason,
            'correction_user_id': self.env.uid,
            'correction_date': fields.Datetime.now(),
        })

        # Log history
        self.env['tlmp.carrier.matching.history'].create({
            'billing_line_id': allocation.billing_line_id.id,
            'transport_order_id': allocation.transport_order_id.id,
            'allocation_id': replacement.id,
            'operation': 'allocation_reversed',
            'from_state': 'confirmed',
            'to_state': 'reversed',
            'operator': self.env.uid,
            'note': reason,
        })

        return {
            'original': allocation,
            'replacement': replacement,
        }

    @api.model
    def update_replacement_amount(self, replacement, new_amount, reason=''):
        """Update the replacement allocation amount."""
        replacement.ensure_one()
        if not replacement.reversed_allocation_id:
            raise models.ValidationError(_(
                'Only replacement allocations can be updated.'))

        old_amount = replacement.allocated_amount
        replacement.write({
            'allocated_amount': new_amount,
            'correction_reason': reason,
            'correction_user_id': self.env.uid,
            'correction_date': fields.Datetime.now(),
        })

        self.env['tlmp.carrier.matching.history'].create({
            'billing_line_id': replacement.billing_line_id.id,
            'transport_order_id': replacement.transport_order_id.id,
            'allocation_id': replacement.id,
            'operation': 'manual_correction',
            'from_state': 'confirmed',
            'to_state': 'confirmed',
            'operator': self.env.uid,
            'note': 'Amount changed: %s -> %s (%s)' % (old_amount, new_amount, reason),
        })

        # Update batch line snapshot if linked
        if replacement.batch_line_id:
            replacement.batch_line_id.write({
                'snapshot_amount': new_amount,
            })

        return replacement
