from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ProductDuplicate(models.Model):
    """
    Model to store duplicate products based on barcode and Linglong code mismatches.
    Products are considered duplicates if they share the same barcode but have different 9-digit Linglong codes.
    """
    _name = 'world.depot.product.duplicate'
    _description = 'Duplicate Products'

    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    product_name = fields.Char(string='Product Name', readonly=True)
    categ_id = fields.Many2one('product.category', string='Category', readonly=True)
    barcode = fields.Char(string='Barcode', readonly=True)
    nine_digit_linglong_code = fields.Char(string="9-Digit Linglong Code")

    def init(self):
        """
        Initialize the model by clearing existing records and populating with new duplicates.
        This method is automatically called during module installation/update.
        """
        # Clear existing duplicate records
        self.search([]).unlink()

        # Find all products with both barcode and Linglong code populated
        products = self.env['world.depot.linglong.product.temp'].search([
            ('barcode', '!=', False),
            ('nine_digit_linglong_code', '!=', False)
        ])

        # Group products by their barcode
        barcode_groups = {}
        for product in products:
            barcode_groups.setdefault(product.barcode, []).append(product)

        # Identify duplicates: same barcode but different Linglong codes
        duplicates = []
        for barcode, product_list in barcode_groups.items():
            if len(product_list) > 1:
                # Check if products have different Linglong codes
                linglong_codes = set(p.nine_digit_linglong_code for p in product_list)
                if len(linglong_codes) > 1:
                    duplicates.extend(product_list)
                product_names = set(p.product_name for p in product_list)
                if len(product_names) > 1:
                    duplicates.extend(product_list)

        # Create records for each duplicate product
        for product in duplicates:
            if not self.search([('barcode', '=', product.barcode),
                                ('nine_digit_linglong_code', '=', product.nine_digit_linglong_code),
                                ('product_name', '=', product.product_name)]):
                self.create({
                    # 'product_id': product.id,
                    'product_name': product.product_name,
                    # 'categ_id': product.categ_id.id,
                    'barcode': product.barcode,
                    'nine_digit_linglong_code': product.nine_digit_linglong_code
                })
