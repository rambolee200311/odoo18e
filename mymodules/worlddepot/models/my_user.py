# -*- coding: utf-8 -*-
from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'

    allowed_product_category_ids = fields.Many2many(
        'product.category', string='Allowed Product Categories'
    )