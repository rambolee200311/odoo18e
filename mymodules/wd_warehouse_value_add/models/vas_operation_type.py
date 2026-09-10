# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class VasOperationType(models.Model):
    _name = 'wd.vas.operation.type'
    _description = 'Warehouse VAS Operation Type'
    _rec_name = 'name'
    _order = 'sequence, name, id'

    name = fields.Char(string='Operation Type', required=True)
    code = fields.Char(string='Code', required=True)
    unit_id = fields.Many2one(
        'world.depot.charge.unit',
        string='Charge Unit',
        required=True,
        ondelete='restrict',
    )
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    @api.constrains('code')
    def _check_code_unique(self):
        for record in self:
            duplicate = self.search([
                ('code', '=', record.code),
                ('id', '!=', record.id),
            ], limit=1)
            if duplicate:
                raise ValidationError('Operation type code must be unique.')
