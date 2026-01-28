import logging
from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta

_logger = logging.getLogger(__name__)


class TransferOrder(models.Model):
    _name = 'world.depot.transfer.order'
    _description = 'Transfer Order'
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = 'billno'

    # Fields
    type = fields.Selection(
        selection=[
            ('type1', 'Type 1'),
            ('type2', 'Type 2'),
            ('type3', 'Type 3'),
        ],
        default='type1',
        string="Order Type",
        required=True,
        tracking=True
    )
    from_location_type = fields.Many2one('stock.location.type', string='From Type', tracking=True)
    to_location_type = fields.Many2one('stock.location.type', string='To Type', tracking=True)
    
    billno = fields.Char(string='Bill No', readonly=True, tracking=True)
    date = fields.Date(string='Order Date', required=True, tracking=True, default=fields.Date.today,
                       help='Planned date')
    t_date = fields.Date(string='Transfer Date', tracking=True, help='Date of transfer')
    project = fields.Many2one('project.project', string='Project', required=True)
    project_category_id = fields.Many2one(
        related='project.category',
        string='Project Category',
        store=True,
        readonly=True
    )
    pick_type = fields.Many2one('stock.picking.type', string='Picking Type', tracking=True,
                                domain=[('code', '=', 'internal')])
    owner = fields.Many2one('res.partner', string='Owner', related='project.owner', tracking=True)
    warehouse = fields.Many2one('stock.warehouse', string='Warehouse', tracking=True,
                                stored=True)
    remark = fields.Text(string='Remark')
    remark1 = fields.Text(string='Remark 1')
    reference = fields.Char(string='Reference', help='Reference for the Order No of Owner', required=True)
    
    confirm_user_id = fields.Many2one(
        'res.users', string='Confirmed By', readonly=True, help="User who confirmed the order."
        , tracking=True)
    confirm_time_user_tz = fields.Datetime(
        string='Confirm Time (User Timezone)', readonly=True, help="Confirmation time in the user's timezone."
        , tracking=True)
    confirm_time_server = fields.Datetime(
        string='Confirm Time (Server)', readonly=True, help="Confirmation time in the server's timezone."
        , tracking=True)

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
    
    stock_picking_id = fields.Many2one('stock.picking', string='Related Picking', readonly=True, tracking=True)
    line_ids = fields.One2many('world.depot.transfer.order.line', 'transfer_order_id', string='Transfer Order Lines', tracking=True)
    doc_ids = fields.One2many('world.depot.transfer.order.docs', 'transfer_order_id', string='Transfer Order Documents', tracking=True)
    charge_ids = fields.One2many('world.depot.transfer.order.charge', 'transfer_order_id', string='Transfer Order Charges', tracking=True)
    
     # Methods
    @api.model
    def create(self, values):
        """Generate bill number and create record."""
        values['billno'] = self.env['ir.sequence'].next_by_code('seq.transfer.order')
        return super(TransferOrder, self).create(values)

    def save_record(self):
        """Custom save method to handle record saving."""
        for record in self:
            
            record.write(record._convert_to_write(record.read()[0]))
        return True
    
    def action_confirm(self):
        """Confirm the transfer order."""
        for record in self:
            if record.state != 'new':
                raise UserError(_('Only new orders can be confirmed.'))
            record.state = 'confirm'
            record.confirm_user_id = self.env.user.id
            now_utc = fields.Datetime.now()
            user_aware_dt = fields.Datetime.context_timestamp(record, now_utc)
            record.confirm_time_user_tz = user_aware_dt.strftime("%Y-%m-%d %H:%M:%S")
            record.confirm_time_server = now_utc
        return True

    def action_cancel_api(self):
        """Cancel the order of api."""
        for record in self:
            if record.state == 'cancel':
                raise UserError(_("This order %s has already been canceled.") % record.reference)
            if record.state != 'new':
                raise UserError(_("Only new orders can be cancelled. (%s)") % record.reference)
            if record.state == 'confirm':
                if record.stock_picking_id:
                    if record.stock_picking_id.state == 'done':
                        raise UserError(
                            _("Cannot cancel the order %s with an active stock picking that is done.") % record.reference)
                    # If the stock picking is not done, delete it
                    try:
                        record.stock_picking_id.unlink()
                    except Exception as e:
                        raise UserError(
                            _("Failed to delete stock picking for order %s: %s") % (record.reference, str(e)))

            record.state = 'cancel'
            now_utc = fields.Datetime.now()
            user_aware_dt = fields.Datetime.context_timestamp(record, now_utc)
            record.confirm_time_user_tz = user_aware_dt.strftime("%Y-%m-%d %H:%M:%S")
            record.confirm_time_server = now_utc

    def action_cancel(self):
        """Cancel the transfer order."""
        for record in self:
            if record.state != 'new':
                raise UserError(_('Only new orders can be cancelled.'))
            record.state = 'cancel'
        return True
    def action_unconfirm(self):
        """Revert the confirmation of the transfer order."""
        for record in self:
            if record.state != 'confirm':
                raise UserError(_('Only confirmed orders can be unconfirmed.'))
            record.state = 'new'
            record.confirm_user_id = False
            record.confirm_time_user_tz = False
            record.confirm_time_server = False
        return True
    
    # Constraints for location types
    @api.constrains('from_location_type', 'to_location_type')
    def _check_location_types(self):
        """Ensure from and to location types are not the same."""
        for record in self:
            if record.from_location_type == record.to_location_type:
                raise ValidationError(_('From Location Type and To Location Type cannot be the same.'))
    
    # Constraint for unique reference within the same project        
    @api.constrains('reference')
    def _check_reference_unique(self):
        """Ensure the reference is unique within the same project."""
        for record in self:
            existing_orders = self.search([
                ('project', '=', record.project.id),
                ('reference', '=', record.reference),
                ('id', '!=', record.id),
                ('state', '!=', 'cancel')
            ])
            if existing_orders:
                raise ValidationError(_('The reference "%s" already exists for this project.') % record.reference)        
    
class TransferOrderLine(models.Model):
    _name = 'world.depot.transfer.order.line'
    _description = 'Transfer Order Line'
    
    transfer_order_id = fields.Many2one('world.depot.transfer.order', string='Transfer Order', required=True, ondelete='cascade')
    project = fields.Many2one(related='transfer_order_id.project', string='Project', store=True, readonly=True)
    project_category_id = fields.Many2one(related='project.category', string='Project Category', store=True,
                                          readonly=True)
    product = fields.Many2one('product.product', string='Product', required=True, tracking=True,
                                 domain="[('categ_id', '=', project_category_id)]")
    quantity = fields.Float(string='Quantity', required=True, default=1.0)
    location_from = fields.Many2one('stock.location', string='Source Location')
    location_to = fields.Many2one('stock.location', string='Destination Location')
    remark = fields.Text(string='Remark')  
    
class TransferOrderDocs(models.Model):
    _name = 'world.depot.transfer.order.docs'
    _description = 'Transfer Order Documents'

    transfer_order_id = fields.Many2one('world.depot.transfer.order', string='Transfer Order', required=True, ondelete='cascade')
    doc_type = fields.Selection(
        selection=[
            ('cmr', 'CMR'),
            ('sn_details', 'SN Details'),
            ('other', 'Other Document'),
        ],
        string="Document Type",
        required=True,
        tracking=True
    )
    description = fields.Text(string='Description')
    file = fields.Binary(string='File')
    filename = fields.Char(string='File name')
    
class TransferOrderCharge(models.Model):
    _name = 'world.depot.transfer.order.charge'
    _description = 'Transfer Order Charge'

    transfer_order_id = fields.Many2one(
        'world.depot.transfer.order',
        string='Transfer Order',
        required=True,
        help='Reference to the related transfer order.'
    )
    charge_item_id = fields.Many2one(
        'world.depot.charge.item',
        string='Charge Item',
        required=True,
        help='The charge item associated with this order.'
    )
    quantity = fields.Float(
        string='Quantity',
        required=True,
        default=1.0,
        help='The quantity of the charge item.'
    )
    charge_unit_name = fields.Char(
        string='Charge Unit',
        related='charge_item_id.unit_id.name',
        readonly=True,
        help='The name of the charge unit, fetched from the related charge item.'
    )
    charge_unit_id = fields.Many2one(
        'world.depot.charge.unit',
        string='Charge Unit Input',
        help='The charge unit selected for this order.'
    )
    unit_price = fields.Monetary(
        string='Unit Price',
        required=True,
        default=0.0,
        help='The price per unit for the charge item.'
    )
    amount = fields.Monetary(
        string='Amount',
        compute='_compute_amount',
        store=True,
        help='The total amount calculated as Quantity x Unit Price.'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
        help='The currency used for this charge.'
    )
    description = fields.Text(
        string='Description',
        help='Additional details or notes about the charge.'
    )

    @api.depends('quantity', 'unit_price')
    def _compute_amount(self):
        """Compute the total amount as Quantity x Unit Price."""
        for record in self:
            record.amount = (record.quantity or 0.0) * (record.unit_price or 0.0)    
