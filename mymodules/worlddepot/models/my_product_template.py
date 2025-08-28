from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ProductTemplate(models.Model):
    _name = 'world.depot.product.template'
    _description = 'Product Import Template'

    # ==== CORE FIELDS ====
    product_name = fields.Char(string='Product Name', required=True)
    product_category = fields.Char(string='Category', required=True)
    barcode = fields.Char(string='Barcode')
    track_by_lot = fields.Boolean(string='Track by Lot', default=False)
    track_by_serial = fields.Boolean(string='Track by Serial', default=False)
    gross_weight = fields.Float(string='Gross Weight (kg)', default=0.0)
    net_weight = fields.Float(string='Net Weight (kg)', default=0.0)
    hs_code = fields.Char(string='HS Code')
    dangerous_goods = fields.Boolean(string='Dangerous Goods', default=False)
    un_code = fields.Char(string='UN Code')
    product_id = fields.Many2one('product.template', string='Linked Product')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('imported', 'Imported'),
        ('error', 'Error')
    ], string='Status', default='draft')
    error_message = fields.Text(string='Import Error')

    # ==== IMPORT METHOD ====
    def action_import_products(self):
        """Create/update products from import records"""
        default_uom = self.env.ref('uom.product_uom_unit')
        ProductTemplate = self.env['product.template']

        for record in self:
            try:
                # Reset status for retries
                record.state = 'draft'
                record.error_message = False

                existing_product = self.env['product.template'].search(
                    [('name', '=', record.product_name)], limit=1
                )
                if existing_product and not record.product_id:
                    record.product_id = existing_product.id

                # Validate category exists
                category = self.env['product.category'].search(
                    [('name', '=', record.product_category)], limit=1
                )
                if not category:
                    raise UserError(
                        _("Category '%s' does not exist. Please create it first.") %
                        record.product_category
                    )

                # Determine tracking type
                tracking = 'serial' if record.track_by_serial else 'lot' if record.track_by_lot else 'none'

                # Prepare product template values
                product_vals = {
                    'name': record.product_name,
                    'categ_id': category.id,
                    'type': 'consu',  # Changed from 'consu' to 'product'
                    'uom_id': default_uom.id,
                    'uom_po_id': default_uom.id,
                    'is_storable': True,
                    'tracking': tracking,
                    'default_code': record.barcode or False,
                    'barcode': record.barcode or False,
                    'weight': record.gross_weight,
                    'sale_ok': True,
                    'purchase_ok': True,
                    'is_dg': record.dangerous_goods,
                    'un_code': record.un_code,
                }

                # Create or update product template
                if not record.product_id:
                    product = ProductTemplate.create(product_vals)
                    record.product_id = product.id
                else:
                    record.product_id.write(product_vals)

                # Update variant-specific fields
                variant = record.product_id.product_variant_ids[:1]
                if variant:
                    variant.write({
                        'hs_code': record.hs_code,
                        'tracking': tracking,
                    })

                record.state = 'imported'

            except Exception as e:
                record.state = 'error'
                record.error_message = str(e)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Import Results'),
                'message': _('Processed %s records. Success: %s, Errors: %s') % (
                    len(self),
                    len(self.filtered(lambda r: r.state == 'imported')),
                    len(self.filtered(lambda r: r.state == 'error'))
                ),
                'sticky': False,
            }
        }
    def action_retry_import(self):
        """Retry import for failed records"""
        return self.action_import_products()
