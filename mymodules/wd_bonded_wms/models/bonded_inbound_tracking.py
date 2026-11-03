# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class BondedInboundTracking(models.Model):
    _name = 'bonded.inbound.tracking'
    _description = 'Bonded Inbound Tracking'
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(string='Inbound Tracking No.', required=True, readonly=True, copy=False, index=True)
    bonded_inbound_id = fields.Many2one('bonded.inbound', string='Bonded Inbound', required=True, ondelete='restrict', index=True)
    customs_file_id = fields.Many2one('bonded.customs.file', string='T1 Customs Declaration', ondelete='restrict', index=True, domain=[('declaration_type', '=', 't1_in')])
    mrn_id = fields.Many2one('bonded.mrn', related='customs_file_id.mrn_id', string='MRN Number', store=True, readonly=True, index=True)
    mrn = fields.Char(related='mrn_id.mrn', string='MRN Number', store=True, readonly=True, index=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Inbound tracking number must be unique!'),
        ('bonded_inbound_uniq', 'unique(bonded_inbound_id)', 'An inbound instruction can only have one tracking number!'),
    ]

    @api.constrains('customs_file_id', 'bonded_inbound_id')
    def check_customs_file(self):
        for rec in self:
            if rec.customs_file_id and rec.customs_file_id != rec.bonded_inbound_id.t1_customs_file_id:
                raise ValidationError(_('The tracking number T1 declaration must match the bonded inbound T1 declaration.'))

    def unlink(self):
        for rec in self:
            raise UserError(_('Inbound tracking numbers cannot be deleted.'))
        return super().unlink()
