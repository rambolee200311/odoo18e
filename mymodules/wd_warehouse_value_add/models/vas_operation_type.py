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
    unit = fields.Char(string='Charge Unit', required=True)
    charge_item_id = fields.Many2one('world.depot.charge.item', string='Charge Item', ondelete='restrict', index=True)
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        ondelete='restrict',
    )
    note = fields.Text(string='Note')
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    is_outbound_palletization = fields.Boolean(string='Outbound Palletization', default=False, index=True)

    def init(self):
        self.env.cr.execute('CREATE UNIQUE INDEX IF NOT EXISTS wd_vas_operation_type_outbound_palletization_uniq ON wd_vas_operation_type (is_outbound_palletization) WHERE is_outbound_palletization')

    @api.constrains('code')
    def _check_code_unique(self):
        for record in self:
            duplicate = self.sudo().search([
                ('code', '=', record.code),
                ('id', '!=', record.id),
            ], limit=1)
            if duplicate:
                raise ValidationError('Operation type code must be unique.')

    @api.constrains('is_outbound_palletization')
    def check_outbound_palletization_unique(self):
        for rec in self:
            if not rec.is_outbound_palletization:
                continue
            duplicate = self.sudo().search([('is_outbound_palletization', '=', True), ('id', '!=', rec.id)], limit=1)
            if duplicate:
                raise ValidationError('Only one operation type can be configured for outbound palletization.')
