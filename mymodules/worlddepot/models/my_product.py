from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'
    is_dg = fields.Boolean(string="Dangerous Goods")
    un_code = fields.Char(
        string="UN Code",
        help="The UN Code for dangerous goods, if applicable"
    )
    pcs_per_pallet = fields.Integer(string="Pcs/Pallet", default=1)
    duty_rate = fields.Float(string="Duty Rate (%)", default=0.0)
    brand = fields.Char(string="Brand")
    nine_digit_linglong_code = fields.Char(string="9-Digit Linglong Code")


class ProductProduct(models.Model):
    _inherit = 'product.product'
    is_dg = fields.Boolean(
        string="Dangerous Goods",
        related='product_tmpl_id.is_dg',
        store=True,  # Crucial for performance
        readonly=True  # Prevents direct writes to variant field
    )
    un_code = fields.Char(
        string="UN Code",
        related='product_tmpl_id.un_code',
        store=True,  # Crucial for performance
        readonly=True  # Prevents direct writes to variant field
    )
    pcs_per_pallet = fields.Integer(
        string="Pcs/Pallet", default=1,
        related='product_tmpl_id.pcs_per_pallet',
        store=True,  # Crucial for performance
        readonly=True  # Prevents direct writes to variant field)
    )
    duty_rate = fields.Float(string="Duty Rate (%)", default=0.0)
    brand = fields.Char(string="Brand")
    nine_digit_linglong_code = fields.Char(string="9-Digit Linglong Code")
