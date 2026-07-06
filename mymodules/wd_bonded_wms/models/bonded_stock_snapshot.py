# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class BondedStockSnapshot(models.Model):
    _name = 'bonded.stock.snapshot'
    _description = 'Bonded Stock Daily Snapshot - 保税库存每日快照'
    _order = 'snapshot_date desc, product_id'
    _rec_name = 'snapshot_date'

    snapshot_date = fields.Date(string='Snapshot Date', required=True, index=True)
    bonded_book_id = fields.Many2one('bonded.book', string='Bonded Book', required=True, index=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    lot_id = fields.Many2one('stock.lot', string='Lot/SN')
    location_id = fields.Many2one('stock.location', string='Location')
    current_customs_status = fields.Selection([
        ('entrepot', 'Entrepot'),
        ('vrij', 'Vrij'),
        ('in_t1_transit', 'In T1 Transit'),
    ], string='Customs Status', required=True)
    quantity = fields.Float(string='Qty', required=True, default=0.0)
    unit_value = fields.Monetary(string='Unit Value', default=0.0)
    total_value = fields.Monetary(string='Total Value', compute='_compute_total', store=True)
    currency_id = fields.Many2one('res.currency', string='Currency')
    mrn = fields.Char(string='MRN')

    @api.depends('quantity', 'unit_value')
    def _compute_total(self):
        for rec in self:
            rec.total_value = rec.quantity * rec.unit_value

    @api.model
    def _cron_generate_snapshot(self):
        """每日23:59生成库存快照 - 策略B: 增量快照(仅当日变动行)"""
        _logger.info('Starting daily bonded stock snapshot...')
        today = fields.Date.today()
        domain = [
            ('quantity', '>', 0),
            ('current_customs_status', 'in', ('entrepot', 'in_t1_transit')),
            '|',
            ('last_snapshot_date', '<', today),
            ('last_snapshot_date', '=', False),
        ]
        stocks = self.env['bonded.stock'].search(domain)
        batch = []
        for stock in stocks:
            batch.append({
                'snapshot_date': today,
                'bonded_book_id': stock.bonded_book_id.id,
                'product_id': stock.product_id.id,
                'lot_id': stock.lot_id.id if stock.lot_id else False,
                'location_id': stock.location_id.id,
                'current_customs_status': stock.current_customs_status,
                'quantity': stock.quantity,
                'unit_value': stock.unit_value,
                'currency_id': stock.currency_id.id,
                'mrn': stock.related_t1_out_mrn or '',
            })
            stock.last_snapshot_date = today
        if batch:
            self.create(batch)
        _logger.info('Snapshot generated: %s records', len(batch))