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
    
    type = fields.Selection(
        selection=[
            ('inbound', 'Inbound'),
            ('service', 'Service'),
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
    
    project = fields.Many2one('project.project', string='Project', required=True)
    project_category_id = fields.Many2one(
        related='project.category',
        string='Project Category',
        store=True,
        readonly=True
    )
    
    from_state=fields.Selection(
        selection=[('salable','Salable'),('Service','Service'),('other','Other')],
        string='From State',
        required=True, )
    to_state=fields.Selection(
        selection=[('salable','Salable'),('Service','Service'),('other','Other')],
        string='To State',
        required=True, )
    
    owner = fields.Many2one('res.partner', string='Owner', related='project.owner', tracking=True)
    warehouse = fields.Many2one('stock.warehouse', string='Warehouse', tracking=True,
                                stored=True)
    remark = fields.Text(string='Remark')
    remark1 = fields.Text(string='Remark 1')
    reference = fields.Char(string='Reference', help='Reference for the Order No of Owner', required=True)
    
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

    picking_ids = fields.Many2one('stock.picking', 'transfer_order_id', string='Related Pickings', readonly=True)
    transfer_order_product_ids = fields.One2many('world.depot.transfer.order.product', 'transfer_order_id', string='Transfer Order Products')
    transfer_order_docs_ids = fields.One2many('world.depot.transfer.order.docs', 'transfer_order_id', string='Transfer Order Documents')
    total_quantity = fields.Float(string='Total Quantity', compute='_compute_total_quantity', store=True)
    
    # check constraints for from_state and to_state
    @api.constrains('from_state', 'to_state')
    def _check_states(self):
        for record in self:
            if record.from_state!='other' and record.to_state!='other':                         
                if record.from_state == record.to_state:
                    raise ValidationError(_("From State and To State cannot be the same."))
                
    def _compute_total_quantity(self):
        for record in self:
            total_qty = 0.0
            for line in record.transfer_order_product_ids:
                total_qty += line.quantity
            record.total_quantity = total_qty            

# transfer order product
class TransferOrderProduct(models.Model):
    _name = 'world.depot.transfer.order.product'
    _description = 'Transfer Order Product'
    
    transfer_order_id = fields.Many2one('world.depot.transfer.order', string='Transfer Order', required=True, ondelete='cascade')
    project = fields.Many2one(related='transfer_order_id.project', string='Project', store=True, readonly=True)
    project_category_id = fields.Many2one(related='project.category', string='Project Category', store=True,
                                          readonly=True)
    product_id = fields.Many2one('product.product', string='Product', required=True,domain="[('categ_id', '=', project_category_id)]")
    description = fields.Text(string='Description')
    quantity = fields.Float(string='Quantity', required=True, default=1.0)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', related='product_id.uom_id', store=True)
    lot_ids = fields.One2many('world.depot.transfer.order.product.lot', 'transfer_order_product_id', string='Product Lots/Serial Numbers')

# transfer order product lot    
class TransferOrderProductLot(models.Model):   
    _name = 'world.depot.transfer.order.product.lot'
    _description = 'Transfer Order Product Lot'
        
    transfer_order_product_id = fields.Many2one('world.depot.transfer.order.product', string='Transfer Order Product', required=True, ondelete='cascade')
    lot_id = fields.Many2one('stock.production.lot', string='Lot/Serial Number', required=True)
    quantity = fields.Float(string='Quantity', required=True, default=1.0)

# transfer order docs    
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