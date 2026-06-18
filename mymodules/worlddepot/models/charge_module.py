from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class ChargeModule(models.Model):
    _name = "world.depot.charge.module"
    _description = "Charge Module"
    _inherit = ['mail.thread']  # Add this line to inherit mail.thread
    _rec_name = "name"

    name = fields.Char(string="Name", required=True, tracking=True)
    type = fields.Selection(
        [("inbound", "Inbound"),
         ("outbound", "Outbound"),
         ('transfer', 'Transfer'),
         ('delivery', 'Delivery'),
         ('transport', 'Transport'),
         ("warehouse", "Warehouse"),
         ('other', 'Other')],
        string='Type', 
        required=True,
        tracking=True
    )
    charge_item_ids = fields.One2many(
        'world.depot.charge.module.item',
        'module_id',
        string='Charge Module Items'
    )
    state = fields.Selection(
        [("draft", "Draft"),
         ("active", "Active"),
         ("cancel", "Cancel")],
        string="State",
        default="draft",
        required=True,
        tracking=True
    )
    description = fields.Text(string="Description")
    
    @api.constrains('name', 'type')
    def _check_unique_name_type(self):
        for record in self:
            existing = self.search([
                ('name', '=', record.name),
                ('type', '=', record.type),
                ('id', '!=', record.id)
            ])
            if existing:
                raise models.ValidationError(f"A Charge Module with name '{record.name}' and type '{record.type}' already exists.")
                    
    def action_activate(self):
        self.ensure_one()
        if self.state != 'draft':
            raise models.UserError("Only draft modules can be activated.")
        self.state = 'active'  # Add this line to actually change the state
            
    def action_deactivate(self):
        self.ensure_one()
        if self.state != 'active':
            raise models.UserError("Only active modules can be deactivated.")            
        self.state = 'draft'        
        
    def action_cancel(self):
        self.ensure_one()
        if self.state == 'cancel':
            raise models.UserError("Module is already cancelled.")
        if self.state != 'draft':
            raise models.UserError("Only draft modules can be cancelled.")    
        self.state = 'cancel'
        
        
    # Override copy method to duplicate charge items as well    
    def copy(self, default=None):
        """Override copy method to append 'Copy' to the name and copy charge items"""
        if default is None:
            default = {}
        
        # Append 'Copy' to the original name
        if 'name' not in default:
            default['name'] = f"{self.name} (Copy)"
            
        default['state'] = 'draft'  # New copy starts in draft state    
        
        # Copy the record first
        new_module = super(ChargeModule, self).copy(default)
        
        # Copy the charge_item_ids (One2many records)
        for item in self.charge_item_ids:
            item.copy({
                'module_id': new_module.id,  # Link to the new module
                'charge_item_id': item.charge_item_id.id,
                'quantity': item.quantity,
                'charge_unit_id': item.charge_unit_id.id,
                'unit_price': item.unit_price,
                'currency_id': item.currency_id.id,
                'description': item.description,
            })
        
        return new_module    

class ChargeModuleItem(models.Model):
    _name = "world.depot.charge.module.item"
    _description = "Charge Module Item"
    
    module_id = fields.Many2one(
        'world.depot.charge.module',
        string='Charge Module',
        required=True,
        help='Reference to the related charge module.'
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
        string='Charge Unit (default)',
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
        for record in self:
            record.amount = record.quantity * record.unit_price