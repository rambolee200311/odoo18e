# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BondedBookLine(models.Model):
    _name = 'bonded.book.line'
    _description = 'Bonded Book Ledger Line'
    _rec_name = 'ref_doc_no'
    _order = 'id desc'

    bonded_book_id = fields.Many2one('bonded.book', string='Bonded Book', required=True, ondelete='restrict', index=True, domain=[('state', '=', 'active')])
    date = fields.Date(string='Date', required=True, default=fields.Date.today, index=True)
    operation_type = fields.Selection([
        ('bonded_inbound', 'Bonded Inbound'),
        ('customs_outbound', 'Customs Outbound'),
        ('t1_outbound', 'T1 Outbound'),
        ('sample_check', 'Sample Check'),
        ('shortage', 'Shortage Disposal'),
        ('rto', 'RTO Return'),
        ('destruction', 'Destruction'),
        ('snapshot', 'Stock Snapshot'),
        ('status_change', 'Status Change'),
    ], string='Operation Type', required=True, index=True)
    product_id = fields.Many2one('product.product', string='Product', required=True, ondelete='restrict', index=True)
    qty_change = fields.Float(string='Qty Change', required=True, default=0.0)
    from_status = fields.Selection([
        ('entrepot', 'Entrepot'),
        ('vrij', 'Vrij'),
        ('in_t1_transit', 'In T1 Transit'),
        ('rto', 'RTO'),
        ('destroyed', 'Destroyed'),
    ], string='From Status', index=True)
    to_status = fields.Selection([
        ('entrepot', 'Entrepot'),
        ('vrij', 'Vrij'),
        ('in_t1_transit', 'In T1 Transit'),
        ('rto', 'RTO'),
        ('destroyed', 'Destroyed'),
    ], string='To Status', index=True)
    direction = fields.Selection([('in', 'In'), ('out', 'Out'), ('none', 'None')], string='Direction', default='none', required=True, index=True)
    ref_doc_no = fields.Char(string='Reference Document No.', index=True)
    inbound_tracking_no = fields.Char(string='Inbound Tracking No.', required=True, index=True)
    customer_batch_no = fields.Char(string='Customer Batch No.', index=True)
    running_balance_qty = fields.Float(string='Running Balance Qty', readonly=True)
    bonded_stock_id = fields.Many2one('bonded.stock', string='Bonded Stock', ondelete='set null', index=True)
    customs_file_id = fields.Many2one('bonded.customs.file', string='Customs Declaration', ondelete='set null', index=True)
    picking_id = fields.Many2one('stock.picking', string='Stock Picking', ondelete='set null', index=True)
    verification_id = fields.Many2one('bonded.verification', string='Verification', ondelete='set null', index=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        balance_cache = {}
        for vals in vals_list:
            key = (
                vals.get('bonded_book_id'),
                vals.get('product_id'),
                vals.get('inbound_tracking_no'),
            )
            if not all(key):
                continue
            if key not in balance_cache:
                previous_line = self.sudo().search([
                    ('bonded_book_id', '=', key[0]),
                    ('product_id', '=', key[1]),
                    ('inbound_tracking_no', '=', key[2]),
                ], order='id desc', limit=1)
                balance_cache[key] = previous_line.running_balance_qty if previous_line else 0.0
            balance_cache[key] += vals.get('qty_change', 0.0)
            vals['running_balance_qty'] = balance_cache[key]
        return super().create(vals_list)

    @api.constrains('inbound_tracking_no')
    def check_inbound_tracking_no(self):
        for rec in self:
            if rec.inbound_tracking_no and not rec.inbound_tracking_no.strip():
                raise ValidationError(_('Inbound tracking no. cannot be empty.'))
