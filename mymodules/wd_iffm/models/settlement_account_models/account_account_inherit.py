from odoo import fields, models


class AccountAccount(models.Model):
    _inherit = "account.account"

    account_category = fields.Selection([
        ("expense", "Expense"),
        ("other", "Other"),
    ], string="Account Category",index=True)
