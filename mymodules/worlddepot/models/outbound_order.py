import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class OutboundOrder(models.Model):
    _name = 'world.depot.outbound.order'
    _description = 'world.depot.outbound.order'
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = 'billno'

    billno = fields.Char(string='BillNo', readonly=True)
    date = fields.Date(string='Order Date', required=True, tracking=True, default=fields.Date.today)
    a_date = fields.Date(string='Arrival Date', required=False, tracking=True)
    owner = fields.Many2one('res.partner', string='Owner', required=True, tracking=True)
    project = fields.Many2one('project.project', string='Project', required=True)
    warehouse = fields.Many2one(comodel_name='stock.warehouse', string='Warehouse')
    remark = fields.Text(string='Remark')
    reference = fields.Char(string='Reference', required=False)

    state = fields.Selection(
        selection=[
            ('new', 'New'),
            ('confirm', 'Confirm'),
            ('cancel', 'Cancel')
        ],
        default='new',
        string="State",
        tracking=True
    )
    outbound_order_product_ids = fields.One2many(
        comodel_name='world.depot.outbound.order.product',
        inverse_name='outbound_order_id',
        string='Outbound Order Products'
    )

    unload_street = fields.Char(string='Street')
    unload_city = fields.Char(string='City')
    unload_state = fields.Char(string='State')
    unload_zip = fields.Char(string='Zip')
    unload_country = fields.Many2one('res.country', string='Country')
    unload_company = fields.Char(string='Company')
    unload_contact = fields.Char(string='Contact')
    unload_phone = fields.Char(string='Phone')
    unload_timeslot = fields.Char(string='Timeslot')
    unload_date = fields.Datetime(string='Date')
    unload_remark = fields.Text(string='Remark')

    picking_PICK = fields.Many2one('stock.picking', string='Picking', readonly=True,
                                   help='Reference to the related Stock Picking')
    picking_PACK = fields.Many2one('stock.picking', string='Packing', readonly=True,
                                   help='Reference to the related Stock Packing')
    picking_Out = fields.Many2one('stock.picking', string='Outbound', readonly=True,
                                  help='Reference to the related Stock Out')

    @api.model
    def create(self, values):
        """
        generate bill number
        """
        times = fields.Date.today()
        values['billno'] = self.env['ir.sequence'].next_by_code('seq.outbound.order', times)
        return super(OutboundOrder, self).create(values)

    def action_confirm(self):
        """
        Confirm the outbound order
        """
        if self.state != 'new':
            raise UserError(_("Outbound order can only be confirmed from 'New' state."))
        else:
            self.state = 'confirm'
        return True

    def action_cancel(self):
        """ Cancel the outbound order
        """
        if self.state not in ['new']:
            raise UserError(_("Outbound order can only be canceled from 'New' state."))
        else:
            self.state = 'cancel'
        return True

    def action_unconfirm(self):
        """ Unconfirm the outbound order
        """
        if self.state != 'confirm':
            raise UserError(_("Outbound order can only be unconfirmed from 'Confirm' state."))
        else:
            self.state = 'new'
        return True

    def action_create_picking_PICK(self):
        """
        Create a stock picking for the outbound order
        """
        if self.state != 'confirm':
            raise UserError(_("Outbound order must be confirmed before creating a stock picking."))
        for record in self:
            # Create stock picking
            picking_type = self.env['stock.picking.type'].search([
                ('sequence_code', '=', 'PICK'),
                ('warehouse_id', '=', record.warehouse.id)
            ], limit=1)
            if not picking_type:
                raise UserError(_("No picking type found for the warehouse."))

            # Check if stock picking already exists
            existing_picking = self.env['stock.picking'].search(
                [('outbound_order_id', '=', record.id),
                 ('picking_type_id', '=', picking_type.id)],
                limit=1)
            if existing_picking:
                raise UserError(_("A stock picking already exists for this Inbound Order."))

            # Create a contact from unload company if it doesn't exist
            contact = self.env['res.partner'].search([
                ('name', '=', record.unload_company)
            ], limit=1)
            if not contact:
                self.env['res.partner'].create({
                    'name': record.unload_company,
                    'street': record.unload_street,
                    'city': record.unload_city,
                    'zip': record.unload_zip,
                    'country_id': record.unload_country.id if record.unload_country else False,
                    'phone': record.unload_phone,
                })

            contact_new = self.env['res.partner'].search([
                ('name', '=', record.unload_company)
            ], limit=1)

            picking = self.env['stock.picking'].create({
                'picking_type_id': picking_type.id,
                'location_id': picking_type.default_location_src_id.id,
                'location_dest_id': picking_type.default_location_dest_id.id,
                'origin': record.billno,
                'partner_id': contact_new.id,
                'outbound_order_id': record.id,
            })

            # Create stock moves
            for product in record.outbound_order_product_ids:
                self.env['stock.move'].create({
                    'name': product.product_id.name,
                    'product_id': product.product_id.id,
                    'product_uom_qty': product.quantity,
                    'product_uom': product.product_id.uom_id.id,
                    'picking_id': picking.id,
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                })
            # Update the stock picking reference in the outbound order
            record.picking_PICK = picking.id

            # return a success message
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Stock Picking Created'),
                    'message': _('Stock picking has been created successfully.'),
                    'sticky': False,
                }
            }


class OutboundOrderProduct(models.Model):
    _name = 'world.depot.outbound.order.product'
    _description = 'Outbound Order Product'

    outbound_order_id = fields.Many2one('world.depot.outbound.order', string='Outbound Order', required=True)
    cntr_no = fields.Char(string='Container No', required=False)
    pallets = fields.Float(string='Pallets', required=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    quantity = fields.Float(string='Quantity', required=True)
    remark = fields.Text(string='Remark')
    is_serial_tracked = fields.Boolean(string='Tracked by Serial', compute='_compute_is_serial_tracked', store=True)
    serial_numbers = fields.Text(string='Serial Numbers',
                                 help="Comma-separated list of serial numbers for the product.")

    @api.depends('product_id')
    def _compute_is_serial_tracked(self):
        for record in self:
            record.is_serial_tracked = record.product_id.tracking == 'serial'
