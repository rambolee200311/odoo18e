# © 2024 Wukong Digital. License LGPL-3.
from odoo import fields, models


class WdMappingCurrencyText(models.Model):
    _name = "wd.mapping.currency_text"
    _description = "Currency Text Mapping"
    _order = "id"

    currency_raw_text = fields.Char(
        string="Currency Raw Text", required=True, index=True
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Matched Currency",
        required=True,
        ondelete="cascade",
    )
    active = fields.Boolean(default=True)
