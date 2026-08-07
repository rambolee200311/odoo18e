from odoo import models, fields


class Terminal(models.Model):
    _name = 'tlmp.transport.terminal'
    _description = 'Terminal'
    _rec_name = "terminal_code"

    terminal_code = fields.Char(string='Code', required=True)
    terminal_name = fields.Char(string='Name')
    terminal_address = fields.Char(string='Address')
    address = fields.Many2one('res.partner', string='Address')
    street = fields.Char(string='Street', related='address.street', readonly=True)
    zip = fields.Char(string='Zip', related='address.zip', readonly=True)
    city = fields.Char(string='City', related='address.city', readonly=True)
    state = fields.Char(string='State', related='address.state_id.name', readonly=True)
    country = fields.Char(string='Country', related='address.country_id.name', readonly=True)
    phone = fields.Char(string='Phone', related='address.phone', readonly=True)
    mobile = fields.Char(string='Mobile', related='address.mobile', readonly=True)