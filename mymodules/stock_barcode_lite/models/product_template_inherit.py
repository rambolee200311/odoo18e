from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplateInherit(models.Model):
    _inherit = 'product.template'

    sunrise_code = fields.Char(string='Sunrise Code')
    sunrise_category_name = fields.Char(string="Sunrise Category Name", related="categ_id.name", store=True)


    @api.constrains('sunrise_code')
    def check_sunrise_code_no_unique(self):
        product_template = self.env['product.template'].sudo().search([('sunrise_code', '=', self.sunrise_code),('id','!=',self.id)])
        if product_template:
            raise ValidationError(_('Sunrise Code must be unique'))