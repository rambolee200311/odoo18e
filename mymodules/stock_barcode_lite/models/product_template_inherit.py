from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplateInherit(models.Model):
    _inherit = 'product.template'

    sunrise_english_name = fields.Char(string="Sunrise English Name", copy=False)
    sunrise_main_uom_name = fields.Char(string="Sunrise Main UOM", copy=False)
    sunrise_uom_conversion_rate = fields.Float(string="Sunrise UOM Conversion Rate", copy=False)
    sunrise_shelf_life_months = fields.Integer(string="Sunrise Shelf Life Months", copy=False)
    sunrise_shelf_life_years = fields.Integer(string="Sunrise Shelf Life Years", copy=False)
    category_name = fields.Char(string="Sunrise Category Name", related="categ_id.name", store=True)

    #sunrise_code = fields.Char(string='Sunrise Code')
    #sunrise_category_name = fields.Char(string="Sunrise Category Name", related="categ_id.name", store=True)


    # @api.constrains('sunrise_code')
    # def check_sunrise_code_no_unique(self):
    #     product_template = self.env['product.template'].sudo().search([('sunrise_code', '=', self.sunrise_code),('id','!=',self.id)])
    #     if product_template:
    #         raise ValidationError(_('Sunrise Code must be unique'))
