from odoo import models, fields, api


class TransportContainer(models.Model):
    _name = 'tlmp.transport.container'
    _description = 'Container'

    name = fields.Char(string='Container No.', required=True)
    request_id = fields.Many2one('tlmp.transport.request', string='Request')
    order_id = fields.Many2one('tlmp.transport.order', string='Order')
    container_type = fields.Selection([
        ('20GP', '20GP'), ('40GP', '40GP'), ('40HQ', '40HQ'),
        ('40HC', '40HC'), ('45HQ', '45HQ'), ('other', 'Other'),
    ], string='Container Type', required=True)
    seal_number = fields.Char(string='Seal No.')
    cargo_weight_kg = fields.Float(string='Cargo Weight (kg)')
    cargo_description = fields.Text(string='Cargo')
    customs_status = fields.Selection([
        ('pending', 'Pending'), ('cleared', 'Cleared'), ('inspection', 'Inspection'),
    ], string='Customs Status', default='pending')
    container_master_id = fields.Many2one('container.master', string='Container Record',
        help='Reference to the global container master record')
    needs_swap = fields.Boolean(string='Needs Swap Container',
        help='Container needs to be swapped before return to shipping line')
    swap_location_id = fields.Many2one('res.partner', string='Swap Location',
        help='Location where the empty container should be returned after swap')
