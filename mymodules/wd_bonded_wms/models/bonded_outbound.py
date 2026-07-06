# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BondedOutbound(models.Model):
    _name = 'bonded.outbound'
    _description = 'Bonded Outbound Instruction - 保税出库指令'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(string='Outbound No.', required=True, copy=False,
                       default=lambda self: _('New'), readonly=True, index=True)
    bonded_book_id = fields.Many2one('bonded.book', string='Bonded Book', required=True,
                                     ondelete='restrict', index=True)
    customs_file_id = fields.Many2one('bonded.customs.file', string='Customs Declaration',
                                      required=True, ondelete='restrict')
    outbound_type = fields.Selection([
        ('l2f', 'L2F (Local Clearance)'),
        ('eu_dispatch', 'EU Dispatch'),
        ('t1_transit', 'T1 Transit'),
        ('destruction', 'Destruction'),
        ('re_export', 'Re-export (RTO)'),
    ], string='Outbound Type', required=True, default='l2f')
    mrn = fields.Char(string='MRN Number',
                      help='Outbound MRN (T1 transit only)')
    expected_date = fields.Date(string='Expected Date', required=True, default=fields.Date.today)
    total_value = fields.Monetary(string='Total Value', required=True, default=0.0)
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.ref('base.EUR').id)
    picking_id = fields.Many2one('stock.picking', string='Stock Picking',
                                 readonly=True, ondelete='restrict')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True, index=True)
    line_ids = fields.One2many('bonded.outbound.line', 'bonded_outbound_id', string='Products')
    remark = fields.Text(string='Remark')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Outbound number must be unique!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('seq.bonded.outbound') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        """确认出库指令 - T1场景自动由customs_approved触发"""
        for rec in self:
            # ---- F-05前置校验 ----
            if rec.customs_file_id.state not in ('customs_approved', 'done'):
                raise UserError(_(
                    'Bonded outbound instruction (%s) cannot be confirmed:\n'
                    'related customs declaration (%s) is in state "%s".'
                    % (rec.name, rec.customs_file_id.declaration_no, rec.customs_file_id.state)
                ))
            # T1出库 + B3出库: 锁定库存
            rec._lock_stock()
            rec.state = 'confirmed'

    def action_start(self):
        self.filtered(lambda r: r.state == 'confirmed').write({'state': 'in_progress'})

    def _action_done(self):
        """指令完成 - 由stock.picking完成时调用"""
        for rec in self:
            if rec.state not in ('confirmed', 'in_progress'):
                raise UserError(_('Only confirmed/in-progress instructions can be set to done.'))
            rec.state = 'done'
            if rec.picking_id:
                for move_line in rec.picking_id.move_line_ids:
                    # 查找对应的bonded.stock
                    bonded_stock = self.env['bonded.stock'].search([
                        ('product_id', '=', move_line.product_id.id),
                        ('location_id', '=', move_line.location_id.id),
                        ('current_customs_status', '=', 'entrepot'),
                        ('locked', '=', True),
                        ('quantity', '>', 0),
                    ], order='inbound_date, id', limit=1)
                    if bonded_stock:
                        to_status = 'in_t1_transit' if rec.outbound_type == 't1_transit' else 'vrij'
                        bonded_stock.write({
                            'current_customs_status': to_status,
                            'locked': False,
                            'related_t1_out_mrn': rec.mrn if rec.outbound_type == 't1_transit' else False,
                        })
                        # 核销记录
                        self.env['bonded.verification'].create({
                            'bonded_book_id': rec.bonded_book_id.id,
                            'verification_type': 'outbound',
                            'customs_file_id': rec.customs_file_id.id,
                            'bonded_stock_id': bonded_stock.id,
                            'from_status': 'entrepot',
                            'to_status': to_status,
                            'quantity': move_line.quantity,
                            'write_off_value': bonded_stock.unit_value * move_line.quantity,
                            'operator_id': self.env.user.id,
                            'mrn': rec.mrn or False,
                        })
            # 释放货值额度 (由value.limit compute自动处理)
            rec.customs_file_id.write({'state': 'done'})

    def action_cancel(self):
        """取消出库指令 - 自动解锁库存(R1)"""
        for rec in self:
            if rec.state not in ('draft',):
                raise UserError(_('Only draft outbound instructions can be cancelled.'))
            # 解锁库存
            bonded_stocks = self.env['bonded.stock'].search([
                ('product_id', 'in', rec.line_ids.mapped('product_id').ids),
                ('locked', '=', True),
                ('current_customs_status', '=', 'entrepot'),
            ])
            bonded_stocks.write({'locked': False})
            # 记录日志
            self.env['bonded.log'].create({
                'model_name': 'bonded.outbound',
                'res_id': rec.id,
                'operation_type': 'action_cancel',
                'operation_detail': _('Cancelled with stock unlock: %s records') % len(bonded_stocks),
            })
            rec.state = 'cancelled'

    def _lock_stock(self):
        """锁定保税库存"""
        for rec in self:
            for line in rec.line_ids:
                stocks = self.env['bonded.stock'].search([
                    ('product_id', '=', line.product_id.id),
                    ('current_customs_status', '=', 'entrepot'),
                    ('locked', '=', False),
                    ('quantity', '>', 0),
                ], order='inbound_date, id')
                total_available = sum(stocks.mapped('quantity'))
                if total_available < line.demand_qty:
                    raise UserError(_(
                        'Insufficient bonded stock for product %s.\n'
                        'Available: %s, Required: %s'
                        % (line.product_id.name, total_available, line.demand_qty)
                    ))
                # 按FIFO锁定
                remaining = line.demand_qty
                for stock in stocks:
                    if remaining <= 0:
                        break
                    lock_qty = min(stock.quantity, remaining)
                    stock.write({'locked': True})
                    remaining -= lock_qty

    def action_create_picking(self):
        """一键创建stock.picking出库单"""
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_('Only confirmed instructions can create pickings.'))
        if self.picking_id:
            raise UserError(_('Stock picking already exists.'))
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': self.env.ref('stock.stock_location_stock').id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'origin': self.name,
            'bonded_outbound_id': self.id,
        })
        for line in self.line_ids:
            self.env['stock.move'].create({
                'name': line.product_id.name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.demand_qty,
                'product_uom': line.uom_id.id or line.product_id.uom_id.id,
                'picking_id': picking.id,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
            })
        self.write({
            'picking_id': picking.id,
            'state': 'in_progress',
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'target': 'current',
        }


class BondedOutboundLine(models.Model):
    _name = 'bonded.outbound.line'
    _description = 'Bonded Outbound Line'
    _order = 'bonded_outbound_id, id'

    bonded_outbound_id = fields.Many2one('bonded.outbound', string='Outbound Instruction',
                                         required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    demand_qty = fields.Float(string='Demand Qty', required=True, default=1.0)
    done_qty = fields.Float(string='Done Qty', compute='_compute_done_qty', store=True)
    uom_id = fields.Many2one('uom.uom', string='UoM', required=True)

    @api.depends('bonded_outbound_id.picking_id.move_ids')
    def _compute_done_qty(self):
        for rec in self:
            if rec.bonded_outbound_id.picking_id:
                moves = rec.bonded_outbound_id.picking_id.move_ids.filtered(
                    lambda m: m.product_id.id == rec.product_id.id and m.state == 'done'
                )
                rec.done_qty = sum(moves.mapped('product_uom_qty'))
            else:
                rec.done_qty = 0.0