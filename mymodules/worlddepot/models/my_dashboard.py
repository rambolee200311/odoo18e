from odoo import models, fields, api


class WorldDepotDashboard(models.TransientModel):
    _name = 'world.deport.dashboard'
    _description = 'World Depot Dashboard'

    inbound_count = fields.Integer(string="Inbound Count")
    outbound_count = fields.Integer(string="Outbound Count")

    @api.model
    def default_get(self, fields):
        """Compute counts dynamically when the dashboard is opened"""
        res = super(WorldDepotDashboard, self).default_get(fields)
        res.update({
            'inbound_count': self.env['world.depot.inbound.order'].search_count([]),
            'outbound_count': self.env['world.depot.outbound.order'].search_count([]),
        })
        return res

    def action_open_inbound(self):
        return self._get_action('world.depot.inbound.order', 'Inbound Order')

    def action_open_outbound(self):
        return self._get_action('world.depot.outbound.order', 'Outbound Order')

    def _get_action(self, model_name, name):
        """Generate common action structure"""
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': model_name,
            'view_mode': 'list,form',
            'domain': [],
            'context': self.env.context,
        }