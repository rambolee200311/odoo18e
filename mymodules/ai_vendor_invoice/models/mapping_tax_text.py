# © 2024 Wukong Digital. License LGPL-3.
from odoo import fields, models


class WdMappingTaxText(models.Model):
    _name = "wd.mapping.tax_text"
    _description = "Tax Text Mapping"
    _order = "id"

    tax_raw_text = fields.Char(string="Tax Raw Text", required=True, index=True)
    tax_id = fields.Many2one(
        "account.tax",
        string="Matched Tax",
        required=True,
        ondelete="cascade",
    )
    active = fields.Boolean(default=True)
