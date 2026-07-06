# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BondedInbound(models.Model):
    _name = 'bonded.inbound'
    _description = 'Bonded Inbound Instruction - 保税入库指令'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(string='Inbound No.', required=True, copy=False,
                       default=lambda self: _('New'), readonly=True, index=True)
    bonded_book_id = fields.Many2one('bonded.book', string='Bonded Book', required=True,
                                     ondelete='restrict', index=True)
    customs_file_id = fields.Many2one('bonded.customs.file', string='Customs Declaration',
                                      required=True, ondelete='restrict',
                                      domain=[('declaration_type', 'in', ('b3_in',))],
                                      context={'default_declaration_type': 'b3_in'})

    # 到仓登记 (Many2many, 支持多T1合并入库)
    gate_arrival_ids = fields.Many2many(
        'gate.arrival',
        'gate_arrival_bonded_inbound_rel',
        'bonded_inbound_id',
        'gate_arrival_id',
        string='Gate Arrivals',
        help='T1 containers arriving at gate. Many2many supports multi-T1 consolidated inbound.'
    )

    # 货物来源(F-06)
    cargo_source = fields.Selection([
        ('port_t1', 'Port T1 Import (First Entry)'),
        ('eu_bonded_t1', 'EU Bonded T1 Transfer'),
        ('direct', 'Direct Duty Paid Entry'),
    ], string='Cargo Source', required=True, default='port_t1')

    expected_date = fields.Date(string='Expected Date', required=True, default=fields.Date.today)
    total_value = fields.Monetary(string='Total Value', required=True, default=0.0)
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.ref('base.EUR').id)

    # 关联仓库单据
    picking_id = fields.Many2one('stock.picking', string='Stock Picking',
                                 readonly=True, ondelete='restrict',
                                 help='Related warehouse receiving order')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True, index=True)

    line_ids = fields.One2many('bonded.inbound.line', 'bonded_inbound_id', string='Products')
    remark = fields.Text(string='Remark')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Inbound number must be unique!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('seq.bonded.inbound') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        """确认入库指令 - 含F-05前置校验"""
        for rec in self:
            # ---- F-05硬校验: customs.file必须是approved ----
            if rec.customs_file_id.state not in ('customs_approved', 'done'):
                raise UserError(_(
                    'Bonded inbound instruction (%s) cannot be confirmed:\n'
                    'related customs declaration (%s) is in state "%s".\n'
                    'Customs approval required first.'
                    % (rec.name, rec.customs_file_id.declaration_no,
                       rec.customs_file_id.state)
                ))
            # ---- Fix-1二次校验: T1入库场景检查所有前置MRN均已闭环 ----
            if rec.customs_file_id.pre_condition == 't1_closed':
                open_mrns = rec.customs_file_id.pre_mrn_ids.filtered(lambda r: r.status != 'closed')
                if open_mrns:
                    open_list = ', '.join(open_mrns.mapped('mrn'))
                    raise UserError(_(
                        'T1 pre-conditions not satisfied.\n'
                        'Following T1 MRN(s) not closed: %s.\n'
                        'All T1s must be closed before inbound confirmation.' % open_list
                    ))
            rec.state = 'confirmed'

    def action_start(self):
        self.filtered(lambda r: r.state == 'confirmed').write({'state': 'in_progress'})

    def action_done(self):
        """指令完成 - 创建bonded.stock + bonded.verification"""
        for rec in self:
            if rec.state != 'in_progress' and rec.state != 'confirmed':
                raise UserError(_('Only confirmed/in-progress instructions can be set to done.'))
            rec.state = 'done'
            if rec.picking_id:
                for move_line in rec.picking_id.move_line_ids:
                    # 创建保税库存属性
                    unit_value = rec.total_value / max(sum(l.planned_qty for l in rec.line_ids), 1.0)
                    # 关联T1 MRN (支持多T1溯源)
                    pre_mrn_ids = False
                    if rec.customs_file_id.pre_mrn_ids:
                        pre_mrn_ids = [(4, m.id) for m in rec.customs_file_id.pre_mrn_ids]
                    bonded_stock = self.env['bonded.stock'].create({
                        'bonded_book_id': rec.bonded_book_id.id,
                        'product_id': move_line.product_id.id,
                        'stock_move_line_id': move_line.id,
                        'lot_id': move_line.lot_id.id if move_line.lot_id else False,
                        'location_id': move_line.location_dest_id.id,
                        'current_customs_status': 'entrepot',
                        'quantity': move_line.quantity,
                        'unit_value': unit_value,
                        'inbound_date': fields.Datetime.now(),
                        'gate_arrival_ids': [(4, ga.id) for ga in rec.gate_arrival_ids],
                        'related_t1_in_mrn_ids': pre_mrn_ids,
                    })
                    # 创建核注记录
                    self.env['bonded.verification'].create({
                        'bonded_book_id': rec.bonded_book_id.id,
                        'verification_type': 'inbound',
                        'customs_file_id': rec.customs_file_id.id,
                        'bonded_stock_id': bonded_stock.id,
                        'from_status': False,
                        'to_status': 'entrepot',
                        'quantity': move_line.quantity,
                        'write_off_value': unit_value * move_line.quantity,
                        'operator_id': self.env.user.id,
                    })
                # 扣减货值额度(由value.limit的compute自动处理)
                rec.customs_file_id.state = 'done'

    def action_cancel(self):
        self.filtered(lambda r: r.state == 'draft').write({'state': 'cancelled'})

    def action_create_picking(self):
        """一键创建stock.picking入库单"""
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_('Only confirmed instructions can create pickings.'))
        if self.picking_id:
            raise UserError(_('Stock picking already exists.'))
        # 创建stock.picking
        picking_vals = {
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': self.env.ref('stock.stock_location_stock').id,
            'origin': self.name,
            'bonded_inbound_id': self.id,
        }
        picking = self.env['stock.picking'].create(picking_vals)
        for line in self.line_ids:
            self.env['stock.move'].create({
                'name': line.product_id.name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.planned_qty,
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


class BondedInboundLine(models.Model):
    _name = 'bonded.inbound.line'
    _description = 'Bonded Inbound Line'
    _order = 'bonded_inbound_id, id'

    bonded_inbound_id = fields.Many2one('bonded.inbound', string='Inbound Instruction',
                                        required=True, ondelete='cascade', index=True)
    customs_file_line_id = fields.Many2one('bonded.customs.file.line', string='Declaration Line',
                                           ondelete='set null')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    planned_qty = fields.Float(string='Planned Qty', required=True, default=1.0)
    done_qty = fields.Float(string='Done Qty', compute='_compute_done_qty', store=True)
    uom_id = fields.Many2one('uom.uom', string='UoM', required=True)

    @api.depends('bonded_inbound_id.picking_id.move_ids')
    def _compute_done_qty(self):
        for rec in self:
            if rec.bonded_inbound_id.picking_id:
                moves = rec.bonded_inbound_id.picking_id.move_ids.filtered(
                    lambda m: m.product_id.id == rec.product_id.id and m.state == 'done'
                )
                rec.done_qty = sum(moves.mapped('product_uom_qty'))
            else:
                rec.done_qty = 0.0