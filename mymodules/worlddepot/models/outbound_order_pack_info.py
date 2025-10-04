from odoo import api, fields, models, _
from odoo.exceptions import UserError


class OutboundOrderPack(models.Model):
    _inherit = 'world.depot.outbound.order'

    outbound_order_pack_ids = fields.One2many(
        'world.depot.outbound.order.pack.info',
        'outbound_order_id',
        string='Pack Information'
    )

    pallets_of_pick = fields.Float(string='Pallets of Pick', help='Number of pallets in the picking', default=0.0)
    pallets_of_packed = fields.Float(string='Pallets of Packed', help='Number of pallets packed', default=0.0)
    # Pack identification
    pack_type = fields.Selection(
        [('box', 'Box'), ('pallet', 'Pallet'), ('carton', 'Carton'), ('bundle', 'Bundle')],
        string='Pack Type',
        required=True,
        default='pallet'
    )

    # Pallet specific fields (only show when pack_type is 'pallet')
    pallet_type = fields.Selection(
        [('standard', 'Standard (120×80 cm)'),
         ('euro', 'Euro (120×100 cm)'),
         ('display', 'Display Pallet'),
         ('custom', 'Custom')],
        string='Pallet Type',
        default='standard'
    )


class OutboundOrderPackInfo(models.Model):
    _name = 'world.depot.outbound.order.pack.info'
    _description = 'Outbound Order Pack Information'
    _order = 'pack_number'

    outbound_order_id = fields.Many2one('world.depot.outbound.order', string='Outbound Order', required=True,
                                        ondelete='cascade')


    pack_number = fields.Char(string='Pack Number', required=True, index=True)



    # Ownership
    pack_owner = fields.Selection(
        [('client', 'Client'), ('warehouse', 'Warehouse'), ('carrier', 'Carrier')],
        string='Pack Owner',
        required=True,
        default='client'
    )

    # Dimensions
    length = fields.Float(string='Length (cm)', help='Length in centimeters')
    width = fields.Float(string='Width (cm)', help='Width in centimeters')
    height = fields.Float(string='Height (cm)', help='Height in centimeters')
    volume = fields.Float(string='Volume (m³)', compute='_compute_volume', store=True, digits=(10, 4))

    # Weight information
    gross_weight = fields.Float(string='Gross Weight (kg)', help='Total weight including packaging')
    net_weight = fields.Float(string='Net Weight (kg)', help='Weight of products only')
    tare_weight = fields.Float(string='Tare Weight (kg)', compute='_compute_tare_weight', store=True,
                               help='Weight of packaging only (Gross - Net)')

    # Product details (better to use relational field instead of text)
    pack_product_ids = fields.One2many(
        'world.depot.outbound.order.pack.product',
        'pack_info_id',
        string='Products in Pack'
    )

    remark = fields.Text(string='Remark')

    # Status fields
    is_loaded = fields.Boolean(string='Loaded', default=False, tracking=True)
    loading_date = fields.Datetime(string='Loading Date', readonly=True)

    # Computed fields
    product_count = fields.Integer(string='Product Varieties', compute='_compute_product_count', store=True)
    total_quantity = fields.Float(string='Total Quantity', compute='_compute_total_quantity', store=True)

    # Computed product description field
    # compute='_compute_product_description',
    product_description = fields.Text(
        string='Product Description',
        store=True,
        help='Description of the products in this pack, formatted as product name (quantity)'
    )

    # Constraints
    '''
    _sql_constraints = [
        ('pack_number_unique', 'unique(outbound_order_id, pack_number)',
         'Pack number must be unique per outbound order!'),
    ]
    '''

    @api.depends('pack_product_ids')
    def _compute_product_description(self):
        """Compute product description in format: Product Name (Quantity)"""
        for record in self:
            descriptions = []
            for product in record.pack_product_ids:
                if product.product_id and product.quantity:
                    descriptions.append(f"{product.product_id.name} ({product.quantity})")

            # Join all product descriptions with comma separation
            record.product_description = ', '.join(descriptions) if descriptions else 'No products'

    @api.constrains('outbound_order_id', 'pack_number')
    def _check_pack_number(self):
        for r in self:
            exist_record = self.search([('outbound_order_id', '=', r.outbound_order_id.id),
                                        ('pack_number', '=', r.pack_number),
                                        ('id', '!=', r.id)])
            if exist_record:
                return UserError('Pack number must be unique per outbound order!')

    @api.depends('length', 'width', 'height')
    def _compute_volume(self):
        for record in self:
            if record.length and record.width and record.height:
                # Convert cm³ to m³ (divide by 1,000,000)
                record.volume = (record.length * record.width * record.height) / 1000000
            else:
                record.volume = 0.0

    @api.depends('gross_weight', 'net_weight')
    def _compute_tare_weight(self):
        for record in self:
            record.tare_weight = record.gross_weight - record.net_weight

    @api.depends('pack_product_ids')
    def _compute_product_count(self):
        for record in self:
            record.product_count = len(record.pack_product_ids)

    @api.depends('pack_product_ids.quantity')
    def _compute_total_quantity(self):
        for record in self:
            record.total_quantity = sum(product.quantity for product in record.pack_product_ids)

    @api.onchange('pack_type')
    def _onchange_pack_type(self):
        """Set default dimensions based on pack type"""
        if self.pack_type == 'pallet':
            self.length = 120.0
            self.width = 80.0
            self.height = 100.0
        elif self.pack_type == 'euro_pallet':
            self.length = 120.0
            self.width = 100.0
            self.height = 100.0
        elif self.pack_type == 'box':
            # Reset to empty for custom box dimensions
            self.length = 0.0
            self.width = 0.0
            self.height = 0.0

    def name_get(self):
        result = []
        for record in self:
            name = f"{record.pack_number} ({record.pack_type})"
            result.append((record.id, name))
        return result


class OutboundOrderPackProduct(models.Model):
    _name = 'world.depot.outbound.order.pack.product'
    _description = 'Products in Outbound Order Pack'

    pack_info_id = fields.Many2one('world.depot.outbound.order.pack.info', string='Pack', required=True,
                                   ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    quantity = fields.Float(string='Quantity', required=True, default=1.0)
    lot_id = fields.Many2one('stock.production.lot', string='Lot/Serial Number',
                             domain="[('product_id', '=', product_id)]")
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', related='product_id.uom_id', store=True)
    weight = fields.Float(string='Unit Weight', related='product_id.weight', store=True)
    total_weight = fields.Float(string='Total Weight', compute='_compute_total_weight', store=True)

    @api.depends('quantity', 'weight')
    def _compute_total_weight(self):
        for record in self:
            record.total_weight = record.quantity * (record.weight or 0.0)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id