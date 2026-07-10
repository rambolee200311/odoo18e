from odoo import fields, models, api, _

class ProjectProjectInherit(models.Model):
    _inherit = 'project.project'

    warehouse = fields.Many2one('stock.warehouse', string='Warehouse', tracking=True)
    inbound_pick_type = fields.Many2one('stock.picking.type', string='Inbound Picking Type', domain=[('code', '=', 'incoming')], tracking=True)
    outbound_pick_type = fields.Many2one('stock.picking.type', string='Outbound Picking Type', domain=[('code', 'in', ['outgoing', 'internal'])], tracking=True)