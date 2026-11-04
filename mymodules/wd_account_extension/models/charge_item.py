# -*- coding: utf-8 -*-

from odoo import fields, models


class ChargeItem(models.Model):
    _inherit = "world.depot.charge.item"

    account_account_id = fields.Many2one("account.account", string="Account", ondelete="restrict", index=True)
