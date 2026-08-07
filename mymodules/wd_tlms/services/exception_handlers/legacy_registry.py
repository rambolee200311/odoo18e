"""Legacy Exception Handler Registry — DEPRECATED.
Kept as fallback for Sprint38. Sprint40: remove this file completely.
Rule Engine takes priority — this only runs when no rule matches."""
from odoo import api, models


class LegacyExceptionHandler(models.AbstractModel):
    _name = 'tlmp.exception.handler.legacy'
    _description = 'Legacy Exception Handler (DEPRECATED — Sprint40 removal)'

    @api.model
    def handle(self, source_model, source_id, context_data=None):
        """Fallback handler. Marks exceptions as created by legacy_handler."""
        ctx = context_data or {}
        # Sprint40: Remove this entire method
        return {'status': 'skipped', 'reason': 'no_rule_match', 'source': source_model}
