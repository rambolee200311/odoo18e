from odoo import api, fields, models, _


class PickupContainerLine(models.Model):
    _name = 'pickup.container.line'
    _description = 'Pickup Container Line'
    _rec_name = 'container_number'
    _order = 'id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    pickup_id = fields.Many2one('import.pickup.requirement',string='Pickup', index=True)
    waybill_container_id = fields.Many2one("world.depot.waybill.container", string="Waybill Container", ondelete="restrict", index=True)
    container_number = fields.Char(string='Container Number', required=True, tracking=True, related='waybill_container_id.container_number')
    container_type = fields.Selection(
        selection=[
            ('20GP', '20GP'),
            ('40GP', '40GP'),
            ('40HQ', '40HQ'),
            ('40HC', '40HC'),
            ('45HQ', '45HQ'),
            ('OT', 'OT'),
            ('FR', 'FR'),
            ('RF', 'RF'),
        ],
        string='Container Type',
        required=True,
        related='waybill_container_id.container_type',
    )
    weight = fields.Float(string='Weight (kg)', required=True,related='waybill_container_id.weight')
    state = fields.Selection([
        ("draft", "Draft"),
        ("planned", "Planned"),
        ("completed", "Completed"),
    ], string="Requirement Container Status", default="draft", required=True, tracking=True, index=True)

