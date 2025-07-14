import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class InboundOrder(models.Model):
    _name = 'world.depot.inbound.order'
    _description = 'Inbound Order'
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = 'billno'

    # Fields
    type = fields.Selection(
        selection=[
            ('inbound', 'Inbound'),
            ('transfer', 'Transfer'),
        ],
        default='inbound',
        string="Order Type",
        required=True,
        tracking=True
    )
    billno = fields.Char(string='Bill No', readonly=True, tracking=True)
    date = fields.Date(string='Order Date', required=True, tracking=True, default=fields.Date.today,
                       help='Planned date')
    a_date = fields.Date(string='Arrival Date', tracking=True, help='Planned date for inbound operation')
    i_date = fields.Date(string='Inbound Date', tracking=True, readonly=True, help='Real date for inbound operation')
    project = fields.Many2one('project.project', string='Project', required=True)
    owner = fields.Many2one('res.partner', string='Owner', related='project.owner', stored=True, tracking=True)
    # terminal = fields.Many2one('res.partner', string='Terminal', tracking=True)
    from_partner = fields.Many2one('res.partner', string='From', tracking=True)
    # other_warehouse = fields.Many2one('res.partner', string='Other Warehouse', tracking=True)
    warehouse = fields.Many2one('stock.warehouse', string='Warehouse', required=True, tracking=True)
    remark = fields.Text(string='Remark')
    reference = fields.Char(string='Reference')
    bl_no = fields.Char(string='Bill of Lading')
    cntr_no = fields.Char(string='Container No')
    pallets = fields.Float(string='Pallets')
    scanning_quantity = fields.Float(string='Scanning Quantity', default=0.0, tracking=True)
    is_adr = fields.Boolean(string='ADR', default=True, tracking=True)

    state = fields.Selection(
        selection=[
            ('new', 'New'),
            ('confirm', 'Confirmed'),
            ('cancel', 'Cancelled')
        ],
        default='new',
        string="State",
        tracking=True
    )
    status = fields.Selection(
        selection=[
            ('planning', 'Planning'),
            ('arrive', 'Arrived'),
            ('inbound', 'Inbound'),
        ],
        default='planning',
        string="Status",
        readonly=True,
        tracking=True
    )
    inbound_order_product_ids = fields.One2many(
        comodel_name='world.depot.inbound.order.product',
        inverse_name='inbound_order_id',
        string='Inbound Order Products'
    )
    stock_picking_id = fields.Many2one(
        'stock.picking', string='Stock Picking', readonly=True,
        help='Reference to the related Stock Picking'
    )

    # Charges
    # 港至仓
    inbound_trucking_charge = fields.Float(
        string='Trucking Charge',
        default=0.0,
        tracking=True
    )

    # 港口其他费用
    inbound_terminal_surcharge = fields.Float(
        string='Terminal Surcharge',
        default=0.0,
        tracking=True
    )
    inbound_terminal_surcharge_remark = fields.Text(
        string='Terminal Surcharge Remark'
    )

    # 入库操作
    inbound_handling_charge = fields.Float(
        string='Inbound Handling',
        default=0.0,
        tracking=True
    )

    # 系统
    inbound_system_file_charge = fields.Float(
        string='System File and Document Admin Fee',
        default=10.0,
        tracking=True
    )

    # 危险品
    inbound_DGD_charge = fields.Float(
        string='Dangerous Goods Declaration Charge',
        default=7.5,
        tracking=True
    )

    inbound_scanning_charge = fields.Float(string='Scanning Charge', default=0.0, tracking=True)

    # Compute adr dgd charge
    @api.depends('is_adr')
    def _compute_is_adr(self):
        """Compute if the order is ADR (Accord européen relatif au transport international des marchandises Dangereuses par Route)."""
        for record in self:
            if record.is_adr:
                record.inbound_DGD_charge = 7.5
            else:
                record.inbound_DGD_charge = 0.0

    @api.depends('project')
    def _compute_charges(self):
        for record in self:
            if record.project:
                record.inbound_trucking_charge = record.project.inbound_trucking_charge
            else:
                record.inbound_trucking_charge = 0.0

    # Methods
    @api.model
    def create(self, values):
        """Generate bill number and create record."""
        values['billno'] = self.env['ir.sequence'].next_by_code('seq.inbound.order')
        return super(InboundOrder, self).create(values)

    def action_confirm(self):
        """Confirm the order."""
        for record in self:
            if record.state != 'new':
                raise UserError(_("Only new orders can be confirmed."))
            record.state = 'confirm'

    def action_cancel(self):
        """Cancel the order."""
        for record in self:
            if record.state != 'new':
                raise UserError(_("Only new orders can be cancelled."))
            record.state = 'cancel'

    def action_unconfirm(self):
        """Unconfirm the order."""
        for record in self:
            if record.state != 'confirm':
                raise UserError(_("Only confirmed orders can be unconfirmed."))
            related_picking = self.env['stock.picking'].search(
                [('inbound_order_id', '=', record.id), ('state', '=', 'done')], limit=1
            )
            if related_picking:
                raise UserError(_("Cannot unconfirm an order with completed stock picking."))

            # Delete related receipts and stock moves not in "done" state
            related_receipts = self.env['stock.picking'].search([
                ('inbound_order_id', '=', record.id),
                ('state', '!=', 'done')
            ])
            for receipt in related_receipts:
                self.env['stock.move'].search([('picking_id', '=', receipt.id)]).unlink()
            related_receipts.unlink()

            record.state = 'new'

    def action_create_stock_picking(self):
        """Create the related stock picking."""
        for record in self:
            if record.state != 'confirm':
                raise UserError(_("Stock picking can only be created from confirmed orders."))
            if not record.bl_no or not record.cntr_no or not record.warehouse:
                raise UserError(
                    _("Bill of Lading, Container No, and Warehouse are required to create a stock picking."))

            # Create stock package
            package_name = f"{record.bl_no} - {record.cntr_no}"
            package_exist = self.env['stock.quant.package'].search([('name', '=', package_name)], limit=1)
            if not package_exist:
                self.env['stock.quant.package'].create({'name': package_name, 'package_use': 'disposable'})

            # Check if stock picking already exists
            existing_picking = self.env['stock.picking'].search([('inbound_order_id', '=', record.id)], limit=1)
            if existing_picking:
                raise UserError(_("A stock picking already exists for this Inbound Order."))

            # Create stock picking
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'incoming'),
                ('warehouse_id', '=', record.warehouse.id)
            ], limit=1)
            if not picking_type:
                raise UserError(_("No incoming picking type found for the selected warehouse."))

            vendor_location = self.env['stock.location'].search([('usage', '=', 'supplier')], limit=1)
            picking = self.env['stock.picking'].create({
                'picking_type_id': picking_type.id,
                'location_id': picking_type.default_location_src_id.id or vendor_location.id,
                'location_dest_id': picking_type.default_location_dest_id.id,
                'origin': record.billno,
                'partner_id': record.owner.id,
                'inbound_order_id': record.id,
            })
            # Create stock moves
            for product in record.inbound_order_product_ids:
                self.env['stock.move'].create({
                    'name': product.product_id.name,
                    'product_id': product.product_id.id,
                    'product_uom_qty': product.quantity,
                    'product_uom': product.product_id.uom_id.id,
                    'picking_id': picking.id,
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                })

            record.stock_picking_id = picking.id

    def action_view_stock_picking(self):
        """View the related stock picking."""
        self.ensure_one()
        action = self.env.ref('stock.action_picking_tree_all').read()[0]
        action['domain'] = [('inbound_order_id', '=', self.id)]
        action['context'] = {'create': False}
        return action

    @api.depends('inbound_order_product_ids')
    def _onchange_sum(self):
        """Update pallets field based on inbound order products."""
        total_pallets = sum(
            product.pallets for product in self.inbound_order_product_ids if product.is_inbound_handling)
        scanning_quantity = sum(product.quantity for product in self.inbound_order_product_ids if product.is_scanning)
        total_inbound_handling_charge = sum(
            product.inbound_handling_charge for product in self.inbound_order_product_ids)
        total_scanning_charge = sum(product.inbound_scanning_charge for product in self.inbound_order_product_ids)
        self.pallets = total_pallets
        self.scanning_quantity = scanning_quantity
        self.inbound_handling_charge = total_inbound_handling_charge
        self.inbound_scanning_charge = total_scanning_charge

    def action_calculate_charges(self):
        """Calculate the total charges for the inbound order."""
        for record in self:
            if record.type == 'inbound':
                record.inbound_trucking_charge = record.project.inbound_trucking_charge
            for detail in record.inbound_order_product_ids:
                # Compute handling and scanning charges for each product
                detail._compute_inbound_handling_charge()
                detail._compute_inbound_scanning_charge()
            # Recalculate total charges
            record.pallets = sum(
                product.pallets for product in record.inbound_order_product_ids if product.is_inbound_handling)
            record.scanning_quantity = sum(
                product.quantity for product in self.inbound_order_product_ids if product.is_scanning)
            record.inbound_handling_charge = sum(
                product.inbound_handling_charge for product in record.inbound_order_product_ids)
            record.inbound_scanning_charge = sum(
                product.inbound_scanning_charge for product in record.inbound_order_product_ids)


class InboundOrderProduct(models.Model):
    _name = 'world.depot.inbound.order.product'
    _description = 'Inbound Order Product'

    inbound_order_id = fields.Many2one('world.depot.inbound.order', string='Inbound Order', required=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    pallets = fields.Float(string='Pallets', required=True, default=1.0)
    quantity = fields.Float(string='Quantity', required=True, default=1.0)
    remark = fields.Text(string='Remark')
    is_serial_tracked = fields.Boolean(string='Tracked by Serial', compute='_compute_is_serial_tracked', store=True)
    is_inbound_handling = fields.Boolean(string='is Handling', default=True, tracking=True)
    inbound_handling_price = fields.Float(string='Handling Price', default=True, tracking=True)
    inbound_handling_unit = fields.Selection(
        selection=[
            ('pallet', 'Per Pallet'),
            ('piece', 'Per Piece')],
        readonly=True,
    )
    inbound_handling_charge = fields.Float(string='Handling Charge', default=0.0, tracking=True)
    is_scanning = fields.Boolean(string='is Scanning', default=True, tracking=True)
    inbound_scanning_price = fields.Float(string='Scanning Price', default=0.0, tracking=True)
    inbound_scanning_charge = fields.Float(string='Scanning Charge', default=0.0, tracking=True)

    # get price from project
    @api.depends('product_id')
    def _compute_is_serial_tracked(self):
        for record in self:
            record.is_serial_tracked = record.product_id.tracking == 'serial'
            record.inbound_handling_price = record.inbound_order_id.project.inbound_handling_price
            record.inbound_handling_unit = record.inbound_order_id.project.inbound_handling_per
            record.inbound_scanning_price = record.inbound_order_id.project.inbound_scanning_price

    # Compute charges based on project settings
    @api.depends('pallets', 'quantity', 'inbound_handling_price')
    def _compute_inbound_handling_charge(self):
        """Compute the inbound handling charge based on pallets, quantity, and project settings."""
        for record in self:
            record.inbound_handling_charge = 0
            record.inbound_handling_price = 0
            if record.is_inbound_handling:
                record.inbound_handling_price = record.inbound_order_id.project.inbound_handling_price
                record.inbound_handling_unit = record.inbound_order_id.project.inbound_handling_per
                if record.inbound_order_id.project.inbound_handling_per == 'pallet':
                    record.inbound_handling_charge = record.pallets * record.inbound_order_id.project.inbound_handling_price
                elif record.inbound_order_id.project.inbound_handling_per == 'piece':
                    record.inbound_handling_charge = record.quantity * record.inbound_order_id.project.inbound_handling_price
                else:
                    record.inbound_handling_unit = False
                    record.inbound_handling_charge = 0
                    record.inbound_handling_price = 0

    # Compute inbound scanning charge based on quantity and project settings
    @api.depends('is_scanning', 'quantity', 'inbound_scanning_price')
    def _compute_inbound_scanning_charge(self):
        """Compute the inbound scanning charge based on quantity and project settings."""
        for record in self:
            record.inbound_scanning_charge = 0
            record.inbound_scanning_price = 0
            if record.is_scanning:
                record.inbound_scanning_price = record.inbound_order_id.project.inbound_scanning_price
                record.inbound_scanning_charge = record.quantity * record.inbound_order_id.project.inbound_scanning_price
            else:
                record.inbound_scanning_charge = 0.0
