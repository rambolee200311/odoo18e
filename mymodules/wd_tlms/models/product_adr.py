# -*- coding: utf-8 -*-
from odoo import models, fields


class ProductProductADR(models.Model):
    _inherit = 'product.product'

    adr_un_number = fields.Char(string='ADR UN Number')
    adr_class_name = fields.Char(string='ADR Class Name')
    adr_packing_group = fields.Selection([
        ('I', 'I'), ('II', 'II'), ('III', 'III'), ('none', 'N/A'),
    ], string='ADR Packing Group')
    adr_class = fields.Char(string='ADR Class/Division')
    is_dangerous_good = fields.Boolean(string='Dangerous Good')
