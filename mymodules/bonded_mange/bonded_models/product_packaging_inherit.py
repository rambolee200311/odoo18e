from odoo import fields, models


class ProductPackaging(models.Model):
    _inherit = "product.packaging"

    estimated_package_weight = fields.Float(string="Estimated Package Weight (kg)", default=0.0)
