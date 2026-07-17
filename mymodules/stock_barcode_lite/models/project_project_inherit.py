from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

class ProjectProjectInherit(models.Model):
    _inherit = 'project.project'

    warehouse = fields.Many2one('stock.warehouse', string='Warehouse', tracking=True)
    inbound_pick_type = fields.Many2one('stock.picking.type', string='Inbound Picking Type', domain=[('code', '=', 'incoming')], tracking=True)
    outbound_pick_type = fields.Many2one('stock.picking.type', string='Outbound Picking Type', domain=[('code', 'in', ['outgoing', 'internal'])], tracking=True)
    package_generation_mode = fields.Selection([('inbound', 'Inbound'), ('picking', 'Picking'), ('none', 'No Package')], string='Package Generation Mode', default='picking', required=True, copy=False, index=True)

