# -*- coding: utf-8 -*-
from odoo import fields, models


class BondedValueLedger(models.Model):
    _name = 'bonded.value.ledger'
    _description = 'Bonded Value Ledger - 货值记录台账'
    _order = 'id desc'

    bonded_book_id = fields.Many2one('bonded.book', string='Bonded Book', required=True, ondelete='restrict', index=True)
    project_id = fields.Many2one('project.project', string='Project', ondelete='restrict', index=True)
    inbound_id = fields.Many2one('bonded.inbound', string='Bonded Inbound', ondelete='restrict', index=True)
    outbound_id = fields.Many2one('bonded.outbound', string='Bonded Outbound', ondelete='restrict', index=True)
    customs_file_id = fields.Many2one('bonded.customs.file', string='Customs Declaration', ondelete='restrict', index=True)
    operation_type = fields.Selection([('reserve', 'Document Reservation'), ('deduct', 'Customs Approved Deduction'), ('release', 'Value Release')], string='Operation Type', required=True, index=True)
    value_amount = fields.Monetary(string='Value Amount', required=True)
    reserved_change = fields.Monetary(string='Reserved Value Change', required=True, default=0.0)
    deducted_change = fields.Monetary(string='Deducted Value Change', required=True, default=0.0)
    reserved_value_after = fields.Monetary(string='Reserved Value After', required=True, readonly=True)
    available_value_after = fields.Monetary(string='Available Value After', required=True, readonly=True)
    operation_datetime = fields.Datetime(string='Operation Time', required=True, readonly=True, default=fields.Datetime.now, index=True)
    operator_id = fields.Many2one('res.users', string='Operator', required=True, readonly=True, default=lambda self: self.env.user, index=True)
    currency_id = fields.Many2one('res.currency', related='bonded_book_id.currency_id', string='Currency', readonly=True)
