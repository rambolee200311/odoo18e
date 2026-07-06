# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class BondedStock(models.Model):
    _name = 'bonded.stock'
    _description = 'Bonded Stock Attribute - 保税库存属性'
    _rec_name = 'product_id'
    _order = 'inbound_date desc, id'

    bonded_book_id = fields.Many2one('bonded.book', string='Bonded Book', required=True,
                                     ondelete='restrict', index=True)
    product_id = fields.Many2one('product.product', string='Product', required=True, index=True)
    stock_move_line_id = fields.Many2one('stock.move.line', string='Stock Move Line',
                                         ondelete='set null', index=True)
    lot_id = fields.Many2one('stock.lot', string='Lot/SN', index=True)
    location_id = fields.Many2one('stock.location', string='Location', required=True, index=True)

    current_customs_status = fields.Selection([
        ('entrepot', 'Entrepot (Bonded)'),
        ('vrij', 'Vrij (Free Circulation)'),
        ('in_t1_transit', 'In T1 Transit'),
        ('rto', 'RTO (Return to Origin)'),
        ('destroyed', 'Destroyed'),
    ], string='Current Customs Status', required=True, default='entrepot', index=True)

    quantity = fields.Float(string='Quantity', required=True, default=0.0)
    unit_value = fields.Monetary(string='Unit Value', required=True, default=0.0)
    total_value = fields.Monetary(string='Total Value', compute='_compute_total_value', store=True)
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.ref('base.EUR').id)
    inbound_date = fields.Datetime(string='Inbound Date', required=True)

    # 溯源
    inbound_verification_id = fields.Many2one('bonded.verification', string='Inbound Verification',
                                              readonly=True)
    gate_arrival_ids = fields.Many2many('gate.arrival', string='Gate Arrivals',
                                        help='T1 source gate arrivals for traceability')
    related_t1_in_mrn_ids = fields.Many2many('customs.file.pre.mrn', string='Related T1 In MRNs',
                                             help='Inbound T1 MRNs for consolidation traceability')
    related_t1_out_mrn = fields.Char(string='T1 Out MRN',
                                     help='Outbound T1 MRN (T1 transit only)')
    locked = fields.Boolean(string='Locked', default=False,
                            help='Locked by outbound instruction')
    last_snapshot_date = fields.Date(string='Last Snapshot Date',
                                     help='For incremental snapshot strategy (R4)')

    _sql_constraints = [
        ('stock_move_line_uniq', 'unique(stock_move_line_id)',
         'Stock move line already has a bonded stock record!'),
    ]

    @api.depends('quantity', 'unit_value')
    def _compute_total_value(self):
        for rec in self:
            rec.total_value = rec.quantity * rec.unit_value