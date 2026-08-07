# -*- coding: utf-8 -*-
from odoo import models, fields, api


class CMRLine(models.Model):
    _name = 'tlmp.cmr.line'
    _description = 'CMR Waybill Cargo Line'
    _order = 'sequence, id'

    cmr_id = fields.Many2one('tlmp.cmr', string='CMR Waybill', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='Sequence', default=10)
    commodity = fields.Char(string='Commodity', required=True)
    sku = fields.Char(string='SKU')
    qty = fields.Float(string='Pallets / Qty', required=True, default=1.0)
    gross_weight_per_unit = fields.Float(string='GW/Unit (kg)')
    gross_weight = fields.Float(string='Gross Weight (kg)', compute='_compute_gross_weight', store=True, readonly=False)
    points = fields.Float(string='Points', default=0.0)

    @api.depends('qty', 'gross_weight_per_unit')
    def _compute_gross_weight(self):
        for line in self:
            if line.gross_weight_per_unit and line.qty:
                line.gross_weight = line.qty * line.gross_weight_per_unit
            elif not line.gross_weight:
                line.gross_weight = 0.0
