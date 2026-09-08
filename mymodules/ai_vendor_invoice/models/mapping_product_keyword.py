# © 2024 Wukong Digital. License LGPL-3.
from odoo import fields, models


class WdMappingProductKeyword(models.Model):
    _name = "wd.mapping.product_keyword"
    _description = "Product Keyword Mapping"
    _order = "id"

    keyword = fields.Char(string="Keyword", required=True, index=True)
    product_id = fields.Many2one(
        "product.product",
        string="Matched Product",
        required=True,
        ondelete="cascade",
    )
    active = fields.Boolean(default=True)
