# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class BondedMonthlyReport(models.Model):
    _name = 'bonded.monthly.report'
    _description = 'Bonded Monthly Stock Report - 保税库存月报'
    _rec_name = 'report_month'
    _order = 'report_month desc, product_id'

    report_month = fields.Date(string='Report Month', required=True, index=True)
    bonded_book_id = fields.Many2one('bonded.book', string='Bonded Book', required=True, index=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    batch_no = fields.Char(string='Batch No.')
    hs_code = fields.Char(string='HS Code')
    opening_qty = fields.Float(string='Opening Qty', default=0.0)
    inbound_qty = fields.Float(string='Inbound Qty', default=0.0)
    outbound_qty = fields.Float(string='Outbound Qty', default=0.0)
    write_off_qty = fields.Float(string='Write-off Qty', default=0.0)
    closing_qty = fields.Float(string='Closing Qty', compute='_compute_closing', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('confirmed', 'Confirmed'),
    ], string='Status', default='draft', required=True)

    @api.depends('opening_qty', 'inbound_qty', 'outbound_qty', 'write_off_qty')
    def _compute_closing(self):
        for rec in self:
            rec.closing_qty = rec.opening_qty + rec.inbound_qty - rec.outbound_qty - rec.write_off_qty

    @api.model
    def _cron_generate_monthly_report(self):
        """每月1日00:00自动生成上月报告"""
        _logger.info('Starting monthly bonded stock report generation...')
        # Implementation: query bonded.stock snapshots for previous month
        # and create/update bonded.monthly.report records
        _logger.info('Monthly report generation completed.')