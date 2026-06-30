from odoo import api, fields, models, _


class OperationOrderContainerLine(models.Model):
    _name = 'operation.order.clearance.container.line'
    _description = 'Operation Order Container Line'

    clearance_id = fields.Many2one('operation.order.clearance',string='Clearance',)
    container_number = fields.Char(string='Container Number')
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
    )
    weight = fields.Float(string='Weight (kg)')