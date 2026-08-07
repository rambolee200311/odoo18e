from odoo import models

from ..business_matrix.rule_engine import BusinessMatrixEngine


class BusinessMatrixService(models.AbstractModel):
    _name = 'tlmp.business.matrix'
    _description = 'Business Matrix Rule Service'

    def evaluate(self, dimensions):
        """Standardized rule engine entry point used by all callers."""
        return BusinessMatrixEngine.validate(self.env, dimensions)
