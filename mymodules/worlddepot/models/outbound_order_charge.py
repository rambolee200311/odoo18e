from odoo import models, fields, api


class OutboundOrderNew(models.Model):
    _inherit = 'world.depot.outbound.order'

    outbound_order_charge_ids = fields.One2many(
        'world.depot.outbound.order.charge',
        'outbound_order_id',
        string='Outbound Order Charges'
    )


class OutboundOrderCharge(models.Model):
    _name = 'world.depot.outbound.order.charge'
    _description = 'Outbound Order Charge'

    outbound_order_id = fields.Many2one(
        'world.depot.outbound.order',
        string='Inbound Order',
        required=True,
        help='Reference to the related outbound order.'
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
