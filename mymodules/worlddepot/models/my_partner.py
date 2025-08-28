from odoo import models, fields, api


class Partner(models.Model):
    _inherit = 'res.partner'

    shipping_line = fields.Boolean(string="Shipping Line", default=False,
                                   help="Indicates if the partner is a shipping line.")
    truck = fields.Boolean(string="Truck Company", default=False, help="Indicates if the partner is a truck company.")
    agency = fields.Boolean(string="Agency", default=False, help="Indicates if the partner is an agency.")
    warehouse = fields.Boolean(string="Warehouse", default=False, help="Indicates if the partner is a warehouse.")
    terminal = fields.Boolean(string="Terminal", default=False, help="Indicates if the partner is a terminal.")
