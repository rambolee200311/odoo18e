from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplateInherit(models.Model):
    _inherit = 'product.template'

    sunrise_english_name = fields.Char(string="Sunrise English Name", copy=False)
    sunrise_chinese_name = fields.Char(string="Sunrise Chinese Name", copy=False)
    sunrise_main_uom_name = fields.Char(string="Sunrise Main UOM", copy=False)
    sunrise_uom_conversion_rate = fields.Float(string="Sunrise UOM Conversion Rate", copy=False)
    sunrise_shelf_life_months = fields.Integer(string="Sunrise Shelf Life Months", copy=False)
    sunrise_shelf_life_years = fields.Integer(string="Sunrise Shelf Life Years", copy=False)
    category_name = fields.Char(string="Sunrise Category Name", related="categ_id.name", store=True)
    organic = fields.Boolean(string="Organic", default=False, copy=False, index=True)
    sunrise_product_category_name = fields.Char(string="Sunrise Product Category", copy=False, index=True)#类别
    gross_weight = fields.Float(string="Gross Weight (kg)", copy=False)
    product_dimensions = fields.Char(string="Product Dimensions (m)", copy=False)

    def action_update_sunrise_organic(self):
        template_model = self.env["product.template"]

        template_ids = template_model.sudo().search([("categ_id.name", "=", "SUNRISE")]).ids
        for rec in template_model.browse(template_ids):
            name_text = " ".join(filter(None, [rec.sunrise_chinese_name, rec.sunrise_english_name, rec.name])).lower()
            organic = "有机" in name_text or "organic" in name_text
            if rec.organic != organic:
                rec.write({"organic": organic})

        return True

    #sunrise_code = fields.Char(string='Sunrise Code')
    #sunrise_category_name = fields.Char(string="Sunrise Category Name", related="categ_id.name", store=True)


    # @api.constrains('sunrise_code')
    # def check_sunrise_code_no_unique(self):
    #     product_template = self.env['product.template'].sudo().search([('sunrise_code', '=', self.sunrise_code),('id','!=',self.id)])
    #     if product_template:
    #         raise ValidationError(_('Sunrise Code must be unique'))
