"""Base exception handler. Sprint38 Rule Engine will replace registry with dynamic rules."""
from odoo import api, models


class BaseExceptionHandler(models.AbstractModel):
    _name = 'tlmp.exception.handler.base'
    _description = 'Base Exception Handler'

    @api.model
    def get_supported_types(self):
        """Return list of exception_type this handler supports."""
        return []

    @api.model
    def detect(self, source_record):
        """Detect exceptions. Return list of dicts:
        [{'exception_type': str, 'priority': str, 'description': str, 'snapshot': dict}]
        """
        return []

    @api.model
    def auto_resolve(self, exception):
        """Auto-resolve if applicable. Return True if resolved."""
        return False
