# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class BondedVerification(models.Model):
    _name = 'bonded.verification'
    _description = 'Bonded Verification - 核注核销记录'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'id'
    _order = 'verification_date desc, id desc'

    bonded_book_id = fields.Many2one('bonded.book', string='Bonded Book', required=True, ondelete='restrict', index=True, domain=[('state', '=', 'active')])
    verification_type = fields.Selection([
        ('inbound', 'Inbound (核注)'),
        ('outbound', 'Outbound (核销)'),
        ('write_off', 'Write-off (处置核销)'),
        ('status_change', 'Status Change'),
    ], string='Verification Type', required=True, index=True)

    customs_file_id = fields.Many2one('bonded.customs.file', string='Customs Declaration',
                                      ondelete='set null')
    mrn = fields.Char(string='MRN Number')
    bonded_stock_id = fields.Many2one('bonded.stock', string='Bonded Stock',
                                      required=True, ondelete='restrict')

    from_status = fields.Selection([
        ('', 'None'),
        ('entrepot', 'Entrepot'),
        ('vrij', 'Vrij'),
        ('in_t1_transit', 'In T1 Transit'),
        ('rto', 'RTO'),
        ('destroyed', 'Destroyed'),
    ], string='From Status', required=True)
    to_status = fields.Selection([
        ('entrepot', 'Entrepot'),
        ('vrij', 'Vrij'),
        ('in_t1_transit', 'In T1 Transit'),
        ('rto', 'RTO'),
        ('destroyed', 'Destroyed'),
    ], string='To Status', required=True)

    quantity = fields.Float(string='Quantity', required=True, default=0.0)
    write_off_value = fields.Monetary(string='Write-off Value')
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.ref('base.EUR').id)
    verification_date = fields.Datetime(string='Verification Date', required=True,
                                        default=fields.Datetime.now)
    operator_id = fields.Many2one('res.users', string='Operator', required=True,
                                  default=lambda self: self.env.user)

    # 复核
    review_user_id = fields.Many2one('res.users', string='Reviewer')
    review_date = fields.Datetime(string='Review Date')
    review_status = fields.Selection([
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Review Status', default='pending', required=True)

    # 处置核销专用
    write_off_type = fields.Selection([
        ('normal_outbound', 'Normal Outbound'),
        ('destruction', 'Destruction'),
        ('re_export', 'Re-export'),
        ('shortage', 'Shortage'),
        ('rto', 'RTO'),
    ], string='Write-off Type')
    customs_approval_no = fields.Char(string='Customs Approval No.',
                                     help='Required for destruction/shortage')
    certificate_file = fields.Binary(string='Certificate File', attachment=True)
    certificate_filename = fields.Char(string='Certificate Filename')

    remark = fields.Text(string='Remark')

    def action_approve(self):
        for rec in self:
            rec.write({'review_status': 'approved', 'review_user_id': self.env.user.id,
                       'review_date': fields.Datetime.now()})
            if rec.verification_type not in ('write_off', 'status_change'):
                continue
            existing_line = self.env['bonded.book.line'].sudo().search([
                ('verification_id', '=', rec.id),
            ], limit=1)
            if existing_line:
                continue
            operation_type = 'status_change'
            if rec.write_off_type == 'destruction':
                operation_type = 'destruction'
            elif rec.write_off_type in ('shortage',):
                operation_type = 'shortage'
            elif rec.write_off_type in ('re_export', 'rto'):
                operation_type = 'rto'
            qty_change = 0.0 if rec.verification_type == 'status_change' else -abs(rec.quantity)
            self.env['bonded.book.line'].create({
                'bonded_book_id': rec.bonded_book_id.id,
                'date': fields.Date.today(),
                'operation_type': operation_type,
                'product_id': rec.bonded_stock_id.product_id.id,
                'qty_change': qty_change,
                'from_status': rec.from_status or False,
                'to_status': rec.to_status,
                'direction': 'none' if qty_change == 0.0 else 'out',
                'ref_doc_no': rec.customs_file_id.declaration_no if rec.customs_file_id else 'VER-%s' % rec.id,
                'inbound_tracking_no': rec.bonded_stock_id.inbound_tracking_no or 'STOCK-%s' % rec.bonded_stock_id.id,
                'customer_batch_no': rec.bonded_stock_id.customer_batch_no,
                'bonded_stock_id': rec.bonded_stock_id.id,
                'customs_file_id': rec.customs_file_id.id if rec.customs_file_id else False,
                'verification_id': rec.id,
            })

    def action_reject(self):
        for rec in self:
            rec.write({'review_status': 'rejected', 'review_user_id': self.env.user.id,
                       'review_date': fields.Datetime.now()})
