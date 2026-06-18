from odoo import models, fields, api, _

class ChargeSummary(models.Model):
    _name = 'world.depot.charge.summary'
    _description = 'Charge Summary for Orders'
    _inherit = ["mail.thread", "mail.activity.mixin"]

    type = fields.Selection(
        [('inbound', 'Inbound Order'), ('outbound', 'Outbound Order')],
        string='Order Type',
        required=True,
        help='Type of order for which charges are summarized'
    )
    
    charge_year = fields.Integer(
        string='Year',
        default=lambda self: fields.Date.context_today(self).year,
        help='Year for charge calculation period'
    )
    
    charge_month = fields.Integer(
        string='Month',       
        default=lambda self: fields.Date.context_today(self).month,
        help='Month for charge calculation period'    
    )
    
    total_amount = fields.Monetary(
        string='Total Amount',
        compute='_compute_total_amount',
        store=True,
        help='Total amount of all charge summary lines'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
        help='Currency used for amount calculations'
    )
    
    charge_summary_line_ids = fields.One2many(
        'world.depot.charge.summary.line',
        'summary_id',
        string='Charge Lines',
        help='Detailed charge items included in this summary'
    )
    
    project=fields.Many2one(
        'project.project',
        string='Project',
        help='Project associated with this charge summary'
    )
    
    @api.depends('charge_summary_line_ids.amount')
    def _compute_total_amount(self):
        """Compute total amount from all summary lines"""
        for record in self:
            record.total_amount = sum(line.amount for line in record.charge_summary_line_ids)
            
    def view_charge_summary_lines(self):
        return {
            'name': _('Charge Summary Lines'),
            'type': 'ir.actions.act_window',
            'res_model': 'world.depot.charge.summary.line',
            'view_mode': 'list',
            'domain': [('summary_id', '=', self.id)],
            'context': {'create': False},
        }        
            
    def action_generate_summary_lines(self):
        """Generate charge summary lines based on order charges"""
        self.ensure_one()
        
        # Clear existing lines first
        self.charge_summary_line_ids.unlink()
        
        # Determine model configuration based on order type
        model_config = {
            'inbound': {
                'parent_model': 'world.depot.inbound.order',
                'charge_model': 'world.depot.inbound.order.charge',
                'parent_field': 'inbound_order_id'
            },
            'outbound': {
                'parent_model': 'world.depot.outbound.order',
                'charge_model': 'world.depot.outbound.order.charge',
                'parent_field': 'outbound_order_id'
            }
        }
        
        config = model_config.get(self.type)
        if not config:
            return
        
        # Build domain filter for orders
        domain = []
        if self.project:
            domain.append(('project', '=', self.project.id))
        if self.charge_year:
            domain.append(('charge_year', '=', self.charge_year))
        if self.charge_month:
            domain.append(('charge_month', '=', self.charge_month))
        
        # Find orders matching the criteria
        orders = self.env[config['parent_model']].search(domain)
        
        if not orders:
            # No orders found for the selected period
            return
        
        # Find all charge records for these orders
        charge_records = self.env[config['charge_model']].search([
            (config['parent_field'], 'in', orders.ids)
        ])
        
        # Create summary lines
        new_lines = []
        for charge in charge_records:
            parent_order = getattr(charge, config['parent_field'])
            line_vals = {
                'summary_id': self.id,
                'order_reference': parent_order.reference or '',
                'charge_item_id': charge.charge_item_id.id,
                'quantity': charge.quantity,
                'charge_unit_id': charge.charge_unit_id.id,
                'unit_price': charge.unit_price,
                'currency_id': charge.currency_id.id,
                'source_charge_id': charge.id,  # Keep reference to original charge
            }
            new_lines.append((0, 0, line_vals))
        
        # Update the summary with new lines
        if new_lines:
            self.charge_summary_line_ids = new_lines

class ChargeSummaryLine(models.Model):
    _name = 'world.depot.charge.summary.line'
    _description = 'Charge Summary Line Item'
    
    summary_id = fields.Many2one(
        'world.depot.charge.summary',
        string='Summary Reference',
        required=True,
        ondelete='cascade',
        help='Parent charge summary record'
    )
    
    order_reference = fields.Char(
        string='Order Reference',
        help='Reference number of the source order'
    )
    
    charge_item_id = fields.Many2one(
        'world.depot.charge.item',
        string='Charge Item',
        required=True,
        help='Type of charge being applied'
    )
    
    charge_item_name = fields.Char(
        string='Charge Name',
        related='charge_item_id.item_name',
        readonly=True,
        store=True,
        help='Name of the charge item'
    )
    
    quantity = fields.Float(
        string='Quantity',
        required=True,
        default=1.0,
        help='Quantity of charge units'
    )
    
    charge_unit_id = fields.Many2one(
        'world.depot.charge.unit',
        string='Unit',
        help='Unit of measurement for the charge'
    )
    
    unit_price = fields.Monetary(
        string='Unit Price',
        required=True,
        default=0.0,
        help='Price per unit'
    )
    
    amount = fields.Monetary(
        string='Amount',
        compute='_compute_amount',
        store=True,
        help='Calculated amount (Quantity × Unit Price)'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
        help='Currency for amount calculations'
    )
    
    source_charge_id = fields.Integer(
        string='Source Charge ID',
        help='ID of the original charge record for tracking'
    )

    @api.depends('quantity', 'unit_price')
    def _compute_amount(self):
        """Calculate line amount"""
        for line in self:
            line.amount = (line.quantity or 0.0) * (line.unit_price or 0.0)