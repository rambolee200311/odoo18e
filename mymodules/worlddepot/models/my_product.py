from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'
    nine_digit_linglong_code = fields.Char(string="9-Digit Linglong Code")

    def cron_update_nine_digit_linglong_code(self):
        # Update all product.product records with the value from product.template
        product_ids = self.env['product.product'].sudo().search([]).ids
        for product in self.env['product.product'].browse(product_ids):
            if not product.nine_digit_linglong_code:
                product.nine_digit_linglong_code = product.product_tmpl_id.nine_digit_linglong_code


class ProductProduct(models.Model):
    _inherit = 'product.product'
    nine_digit_linglong_code = fields.Char(string="9-Digit Linglong Code")
