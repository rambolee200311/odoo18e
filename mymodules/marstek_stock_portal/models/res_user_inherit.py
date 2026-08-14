from odoo import api, fields, models

class ResUsersInherit(models.Model):
    _inherit = "res.users"

    marstek_owner_id = fields.Many2one('res.partner', string='Marstek Portal Owner', index=True, copy=False)
