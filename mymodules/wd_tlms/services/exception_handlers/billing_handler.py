"""Billing exception handler — detects amount mismatches and duplicate invoices."""
import json
from odoo import api, models


class BillingExceptionHandler(models.AbstractModel):
    _name = 'tlmp.exception.handler.billing'
    _description = 'Billing Exception Handler'
    _inherit = 'tlmp.exception.handler.base'

    @api.model
    def get_supported_types(self):
        return ['AMOUNT_MISMATCH', 'DUPLICATE_INVOICE']

    @api.model
    def detect(self, source_record):
        results = []
        # Amount mismatch: allocation vs billing line
        for line in source_record.line_ids:
            variance = abs((line.line_total or 0.0) - (line.allocated_total or 0.0))
            if variance > 0.01 and variance / max(line.line_total, 1.0) > 0.05:
                results.append({
                    'exception_type': 'AMOUNT_MISMATCH',
                    'priority': 'urgent',
                    'description': 'Amount mismatch: billing=%.2f vs allocated=%.2f (diff=%.2f)' % (
                        line.line_total, line.allocated_total, variance),
                    'snapshot': {
                        'billing_line_id': line.id,
                        'line_total': line.line_total,
                        'allocated_total': line.allocated_total,
                        'variance': variance,
                    },
                })
        return results

    @api.model
    def auto_resolve(self, exception):
        if exception.exception_type == 'DUPLICATE_INVOICE':
            exception.resolution_note = 'System auto-rejected: duplicate invoice'
            exception.action_auto_resolve()
            return True
        return False
