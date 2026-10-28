# -*- coding: utf-8 -*-
from odoo import api, fields, models


class BondedChargeUnit(models.Model):
    _name = 'bonded.charge.unit'
    _description = 'Bonded Charge Unit'
    _order = 'id desc'

    name = fields.Char(string='Name', required=True, index=True)
    code = fields.Char(string='Code', required=True, index=True)
    active = fields.Boolean(string='Active', default=True)

    _sql_constraints = [('bonded_charge_unit_code_uniq', 'unique(code)', 'Bonded charge unit code must be unique!')]


class BondedChargeItem(models.Model):
    _name = 'bonded.charge.item'
    _description = 'Bonded Charge Item'
    _order = 'id desc'

    name = fields.Char(string='Name', required=True, index=True)
    code = fields.Char(string='Code', required=True, index=True)
    charge_unit_id = fields.Many2one('bonded.charge.unit', string='Charge Unit', required=True, ondelete='restrict', index=True)
    default_unit_price = fields.Monetary(string='Default Unit Price', default=0.0)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.ref('base.EUR').id)
    active = fields.Boolean(string='Active', default=True)

    _sql_constraints = [('bonded_charge_item_code_uniq', 'unique(code)', 'Bonded charge item code must be unique!')]


class BondedChargeLine(models.Model):
    _name = 'bonded.charge.line'
    _description = 'Bonded Charge Line'
    _rec_name = 'charge_item_id'
    _order = 'id desc'

    charge_item_id = fields.Many2one('bonded.charge.item', string='Charge Item', required=True, ondelete='restrict', index=True)
    charge_unit_id = fields.Many2one('bonded.charge.unit', string='Charge Unit', related='charge_item_id.charge_unit_id', store=True, readonly=True, index=True)
    bonded_book_id = fields.Many2one('bonded.book', string='Bonded Book', ondelete='restrict', index=True)
    customs_file_id = fields.Many2one('bonded.customs.file', string='Customs Declaration', ondelete='set null', index=True)
    bonded_inbound_id = fields.Many2one('bonded.inbound', string='Bonded Inbound', ondelete='set null', index=True)
    bonded_outbound_id = fields.Many2one('bonded.outbound', string='Bonded Outbound', ondelete='set null', index=True)
    gate_arrival_id = fields.Many2one('gate.arrival', string='Gate Arrival', ondelete='set null', index=True)
    charge_date = fields.Date(string='Charge Date', required=True, default=fields.Date.today, index=True)
    quantity = fields.Float(string='Quantity', required=True, default=1.0)
    unit_price = fields.Monetary(string='Unit Price', required=True, default=0.0)
    amount = fields.Monetary(string='Amount', compute='_compute_amount', store=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.ref('base.EUR').id)
    remark = fields.Text(string='Remark')
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company, index=True)

    @api.depends('quantity', 'unit_price')
    def _compute_amount(self):
        for rec in self:
            rec.amount = rec.quantity * rec.unit_price
