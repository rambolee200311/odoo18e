"""Exception Handler Registry — maps exception_type to handler.
Sprint38: Rule Engine replaces this registry with dynamic rules."""
from odoo import api, models


class ExceptionHandlerRegistry(models.AbstractModel):
    _name = 'tlmp.exception.handler.registry'
    _description = 'Exception Handler Registry'

    @api.model
    def discover_handlers(self):
        """Discover all registered handler models."""
        handlers = self.env['ir.model'].search([
            ('model', 'like', 'tlmp.exception.handler.%'),
            ('model', '!=', 'tlmp.exception.handler.base'),
            ('model', '!=', 'tlmp.exception.handler.registry'),
        ])
        return [self.env[h.model] for h in handlers]

    @api.model
    def get_handler(self, exception_type):
        """Find handler for given exception_type."""
        for handler in self.discover_handlers():
            if exception_type in handler.get_supported_types():
                return handler
        return None
