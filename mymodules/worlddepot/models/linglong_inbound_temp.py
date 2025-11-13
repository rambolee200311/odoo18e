from odoo import api, fields, models, _
from odoo.exceptions import UserError


class LinglongProductTemp(models.Model):
    _name = 'world.depot.linglong.product.temp'
    _description = 'Linglong Product Temporary Data'

    departure_date = fields.Date(string='Departure Date')
    barcode = fields.Char(string='Barcode')
    nine_digit_linglong_code = fields.Char(string="9-Digit Linglong Code")
    product_name = fields.Char(string='Product Name')
    quantity = fields.Float(string='Quantity')
    hs_code = fields.Char(string='HS Code')
    invoice_no = fields.Char(string='Invoice No')
    bill_of_lading = fields.Char(string='Bill of Lading')
    brand = fields.Char(string='Brand')
    category = fields.Char(string='Category')
    product_id = fields.Many2one('product.template', string='Linked Product')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('imported', 'Imported'),
        ('error', 'Error')
    ], string='Status', default='draft')
    error_message = fields.Text(string='Import Error')

    def action_import_inbound_order(self):
        selecteds = self.browse(self.env.context.get('active_ids'))

        # Ensure at least one record is selected
        if not selecteds:
            raise UserError("Please select at least one record.")

        grouped_records = selecteds.read_group(
            domain=[('state', '!=', 'imported'), ('barcode', '!=', False)],
            fields=['barcode'],
            groupby=['barcode']
        )
        for group in grouped_records:
            barcode = group['barcode']
            if not barcode == '':
                records = self.search([('barcode', '=', barcode), ('state', '!=', 'imported')])
                for record in records:
                    if not self._import_products(record):
                        raise UserError(_("Error importing product: %s") % record.error_message)
                    else:
                        records.write({'state': 'imported'})

        # Return success notification
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Inbound orders have been successfully imported.'),
                'type': 'success',  # Types: success, warning, danger, info
                'sticky': False,  # If True, the notification stays until manually closed
            },
        }

    def action_import_inbound_order_old(self):
        """Import inbound orders based on temporary data."""
        # Group records by bill_of_lading
        grouped_records = self.read_group(
            domain=[('state', '!=', 'imported')],
            fields=['bill_of_lading'],
            groupby=['bill_of_lading']
        )
        for group in grouped_records:
            bill_of_lading = group['bill_of_lading']
            records = self.search([('bill_of_lading', '=', bill_of_lading), ('state', '!=', 'imported')])

            # Prepare inbound order values
            inbound_order_vals = {
                'type': 'inbound',
                'project': self.env['project.project'].search([('name', '=', 'LINGLONG')], limit=1).id,
                'reference': bill_of_lading,
                'bl_no': bill_of_lading,
                'date': records[0].departure_date,
                'invoice_no': records[0].invoice_no,
                'inbound_order_product_ids': [],
            }

            for record in records:
                if not self._import_products(record):
                    raise UserError(_("Error importing product: %s") % record.error_message)

                # Prepare pallet and product values
                pallet_vals = {
                    'pallets': 1,
                    'inbound_order_product_pallet_ids': [
                        (0, 0, {
                            'product_id': record.product_id.id,
                            'quantity': record.quantity,
                        })
                    ],
                }
                inbound_order_vals['inbound_order_product_ids'].append((0, 0, pallet_vals))

            # Create inbound order
            self.env['world.depot.inbound.order'].create(inbound_order_vals)
            records.write({'state': 'imported'})

        # Return success notification
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Inbound orders have been successfully imported.'),
                'type': 'success',  # Types: success, warning, danger, info
                'sticky': False,  # If True, the notification stays until manually closed
            },
        }

    def _import_products(self, record):
        """Create or update products from temporary data."""
        default_uom = self.env.ref('uom.product_uom_unit')
        ProductTemplate = self.env['product.template']

        try:
            # Reset status for retries
            record.state = 'draft'
            record.error_message = False

            # Validate category
            category = self.env['product.category'].search([('name', '=', record.category)], limit=1)
            if not category:
                raise UserError(_("Category not found: %s") % record.category)

            # Search for existing product
            existing_product = ProductTemplate.search(
                [('barcode', '=', record.barcode)], limit=1
            )

            if not existing_product:
                default_code = record.barcode[6:-1] if record.barcode else False
                # Create new product
                product_vals = {
                    'name': 'Linglong ' + record.product_name,
                    'categ_id': category.id,
                    'type': 'consu',
                    'uom_id': default_uom.id,
                    'uom_po_id': default_uom.id,
                    'is_storable': True,
                    'tracking': 'lot',
                    'default_code': default_code or False,
                    'barcode': record.barcode or False,
                    'sale_ok': True,
                    'purchase_ok': True,
                    'hs_code': record.hs_code or False,
                    'brand': record.brand or False,
                    'nine_digit_linglong_code': record.nine_digit_linglong_code or False,
                }
                existing_product = ProductTemplate.create(product_vals)

            # Link product to the record
            record.product_id = existing_product.id
            return True
        except Exception as e:
            record.state = 'error'
            record.error_message = str(e)
            return False

    def action_update_nine_digit_linglong_code(self):
        # Define the domain to find products with missing nine_digit_linglong_code
        # domain = [('categ_id', '=', 11), ('nine_digit_linglong_code', '=', False)]
        domain = [('categ_id', '=', 11)]
        ProductTemplate = self.env['product.template'].search(domain)

        # Fetch barcodes in bulk to avoid redundant searches
        barcodes = ProductTemplate.read(['id', 'barcode'])

        # Prepare updates
        updates = {}
        for product in barcodes:
            if product['barcode']:
                # Search for the corresponding nine_digit_linglong_code
                temp_record = self.search([('barcode', '=', product['barcode'])], limit=1)
                if temp_record and temp_record.nine_digit_linglong_code:
                    updates[product['id']] = temp_record.nine_digit_linglong_code

        # Perform batch updates
        for product_id, nine_digit_code in updates.items():
            self.env['product.template'].browse(product_id).write({'nine_digit_linglong_code': nine_digit_code})
            self.env['product.product'].search([('product_tmpl_id', '=', product_id)]).write({'nine_digit_linglong_code': nine_digit_code})
