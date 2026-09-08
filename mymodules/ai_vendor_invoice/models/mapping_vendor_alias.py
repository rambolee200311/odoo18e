# © 2024 Wukong Digital. License LGPL-3.
from odoo import fields, models


class WdMappingVendorAlias(models.Model):
    _name = "wd.mapping.vendor_alias"
    _description = "Vendor Alias Mapping"
    _order = "id"

    alias_text = fields.Char(string="Alias Text", required=True, index=True)
    partner_id = fields.Many2one(
        "res.partner",
        string="Matched Partner",
        required=True,
        ondelete="cascade",
    )
    active = fields.Boolean(default=True)
