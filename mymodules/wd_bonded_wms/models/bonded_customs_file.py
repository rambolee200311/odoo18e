# -*- coding: utf-8 -*-
import json
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class BondedCustomsFile(models.Model):
    _name = 'bonded.customs.file'
    _description = 'Customs Declaration File - 海关文件表头 (SAD/C88)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'declaration_no'
    _order = 'declaration_date desc, id desc'

    # ===== 账册关联 =====
    bonded_book_id = fields.Many2one('bonded.book', string='Bonded Book', required=True,
                                     ondelete='restrict', index=True)

    # ===== 申报类型 =====
    declaration_type = fields.Selection([
        ('t1_in', 'T1 Transit Inbound'),
        ('b3_in', 'B3 Bonded Inbound'),
        ('b3_out', 'B3 Customs Clearance (L2F)'),
        ('t1_out', 'T1 Transit Outbound'),
        ('ex', 'EU Dispatch'),
        ('destruction', 'Destruction'),
    ], string='Declaration Type', required=True, index=True, tracking=True)

    # ===== SAD/C88 Core Fields =====
    mrn = fields.Char(string='MRN Number', index=True,
                      help='Movement Reference Number (T1 only)')
    declaration_no = fields.Char(string='Declaration No. (Box3)', required=True, copy=False,
                                 default=lambda self: _('New'), readonly=True, index=True)
    customs_code = fields.Char(string='Customs Code (Box5)', required=True, index=True,
                               help='e.g. NLAMS001')
    consignor_eori = fields.Char(string='Consignor EORI (Box8)', required=True)
    consignee_eori = fields.Char(string='Consignee EORI (Box9)', required=True)
    declarant_eori = fields.Char(string='Declarant EORI', required=True)
    procedure_code = fields.Char(string='Procedure Code (Box37)', required=True, default='4000C51',
                                 help='e.g. 4000C51 for bonded warehouse')
    previous_doc_no = fields.Char(string='Previous Document No. (Box40)',
                                  help='T1 inbound: fill with handover DO number')
    bonded_warehouse_no = fields.Char(string='Bonded Warehouse No. (Box49)')

    # ===== 运输信息 =====
    origin_country_id = fields.Many2one('res.country', string='Country of Origin', required=True)
    destination_country_id = fields.Many2one('res.country', string='Country of Destination', required=True)
    transport_mode = fields.Selection([
        ('sea', 'Sea'),
        ('road', 'Road'),
        ('air', 'Air'),
        ('rail', 'Rail'),
    ], string='Transport Mode', required=True, default='sea')
    estimated_distance_km = fields.Float(string='Estimated Distance (km)',
                                         help='Used for transit_deadline calculation. Road: +1 day per 500km')
    transit_deadline = fields.Datetime(string='Transit Deadline',
                                       help='Auto-calculated from transport_mode + distance, manually adjustable')

    total_packages = fields.Float(string='Total Packages', required=True, default=0.0)
    total_gross_weight = fields.Float(string='Total Gross Weight (kg)', required=True, default=0.0)
    invoice_amount = fields.Monetary(string='Invoice Amount', required=True, default=0.0)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                  default=lambda self: self.env.ref('base.EUR').id)
    declaration_date = fields.Datetime(string='Declaration Date')

    # ===== 前置条件 (F-02) =====
    pre_condition = fields.Selection([
        ('none', 'No Pre-condition'),
        ('t1_closed', 'T1 Must Be Closed'),
    ], string='Pre-condition Type', default='none', required=True,
        help='b3_in with T1 source: must select t1_closed')
    pre_satisfied_date = fields.Datetime(string='Pre-condition Satisfied Date', readonly=True)
    pre_mrn_ids = fields.One2many('customs.file.pre.mrn', 'customs_file_id', string='Pre-condition MRNs',
                                  help='Required when pre_condition=t1_closed. Supports multiple T1 MRNs for consolidated inbound.')
    t1_closed_date = fields.Datetime(string='T1 Closed Date', readonly=True)

    # ===== 状态 =====
    state = fields.Selection([
        ('draft', 'Draft'),
        ('to_be_submitted', 'To Be Submitted'),
        ('submitted', 'Submitted'),
        ('customs_approved', 'Customs Approved'),
        ('customs_rejected', 'Customs Rejected'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True, index=True)

    # ===== 海关回执 =====
    rejection_reason = fields.Text(string='Rejection Reason', readonly=True)
    approval_no = fields.Char(string='Approval No.', readonly=True)
    approval_date = fields.Datetime(string='Approval Date', readonly=True)
    declaration_file = fields.Binary(string='Declaration File', attachment=True)
    response_file = fields.Binary(string='Customs Response File', attachment=True)
    response_filename = fields.Char(string='Response Filename')

    # ===== 关联 =====
    line_ids = fields.One2many('bonded.customs.file.line', 'customs_file_id', string='Declaration Lines')
    handover_id = fields.Many2one('operation.order.handover', string='Handover',
                                  help='Related import handover (data flows from handover)')
    gate_arrival_ids = fields.One2many('gate.arrival', 'customs_file_id', string='Gate Arrivals',
                                       help='T1 only: container arrival records linked to this T1')

    remark = fields.Text(string='Remark')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    _sql_constraints = [
        ('declaration_no_uniq', 'unique(declaration_no)', 'Declaration number must be unique!'),
    ]

    # ===== Sequence =====
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('declaration_no', _('New')) == _('New'):
                seq_code = {
                    't1_in': 'seq.customs.file.t1_in',
                    'b3_in': 'seq.customs.file.b3_in',
                    'b3_out': 'seq.customs.file.b3_out',
                    't1_out': 'seq.customs.file.t1_out',
                    'ex': 'seq.customs.file.ex',
                    'destruction': 'seq.customs.file.destruction',
                }.get(vals.get('declaration_type'))
                if seq_code:
                    vals['declaration_no'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')
            # Auto-calculate transit_deadline
            if vals.get('transport_mode') and not vals.get('transit_deadline'):
                vals['transit_deadline'] = self._compute_transit_deadline(
                    vals.get('transport_mode'), vals.get('estimated_distance_km', 0.0))
        return super().create(vals_list)

    # ===== State Actions =====
    def action_submit(self):
        """提交申报 - 含前置条件校验(F-02/Fix-1)"""
        for rec in self:
            # ---- Fix-1: B3申报校验所有前置MRN均已关闭 ----
            if rec.declaration_type == 'b3_in' and rec.pre_condition == 't1_closed':
                if not rec.pre_mrn_ids:
                    raise UserError(_(
                        'T1 inbound scenario requires at least one pre-condition MRN. '
                        'Please specify the T1 MRN(s) that must be closed first.'))
                open_mrns = rec.pre_mrn_ids.filtered(lambda r: r.status != 'closed')
                if open_mrns:
                    open_list = ', '.join(open_mrns.mapped('mrn'))
                    raise UserError(_(
                        'The following T1 MRN(s) have NOT been closed yet: %s\n'
                        'B3 bonded inbound declaration is NOT ALLOWED until ALL pre-condition T1s '
                        'are closed. Current customs status: IVV (in transit).' % open_list
                    ))
                rec.pre_satisfied_date = fields.Datetime.now()
            # ---- 货值校验 ----
            if not rec._check_value_limit():
                raise UserError(_('Value limit check failed. Please verify bonded.value.limit.'))
            # ---- 商品备案校验 ----
            if not rec._check_product_filing():
                raise UserError(_('Product filing check failed. Please verify bonded.product records.'))
            rec.write({
                'state': 'submitted',
                'declaration_date': fields.Datetime.now(),
            })

    def action_approve(self):
        """模拟海关审批通过"""
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_('Only submitted declarations can be approved.'))
            rec.write({
                'state': 'customs_approved',
                'approval_date': fields.Datetime.now(),
                'approval_no': self.env['ir.sequence'].next_by_code('seq.customs.approval') or 'APP-' + fields.Datetime.now().strftime('%Y%m%d%H%M%S'),
            })
            # T1场景: 自动创建gate.arrival预约
            if rec.declaration_type in ('t1_in',):
                rec._create_gate_arrival_reservation()
            # 自动创建保税指令
            if rec.declaration_type in ('b3_in',):
                rec._create_bonded_inbound()
            elif rec.declaration_type in ('b3_out', 'ex', 'destruction'):
                rec._create_bonded_outbound()
            elif rec.declaration_type == 't1_out':
                rec._create_bonded_outbound_t1()

    def action_reject(self, reason=''):
        """模拟海关驳回"""
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_('Only submitted declarations can be rejected.'))
            rec.write({
                'state': 'customs_rejected',
                'rejection_reason': reason or _('Rejected by customs authority.'),
            })
            # T1出库驳回: 自动解锁库存(Fix-2)
            if rec.declaration_type == 't1_out':
                rec._unlock_stock_on_rejection()

    def action_done(self):
        """T1核销闭环 / B3完成"""
        for rec in self:
            if rec.state != 'customs_approved':
                raise UserError(_('Only approved declarations can be set to done.'))
            rec.write({'state': 'done'})
            if rec.declaration_type in ('t1_in',):
                rec.write({'t1_closed_date': fields.Datetime.now()})
                # 通知关联的gate.arrival
                rec.gate_arrival_ids.write({'state': 'closed', 't1_closed_date': fields.Datetime.now()})

    def action_cancel(self):
        for rec in self:
            if rec.state not in ('draft', 'to_be_submitted', 'submitted'):
                raise UserError(_('Only draft/to_submit/submitted declarations can be cancelled.'))
            rec.write({'state': 'cancelled'})

    # ===== Internal Methods =====
    def _check_value_limit(self):
        """校验货值额度"""
        self.ensure_one()
        limits = self.env['bonded.value.limit'].search([
            ('bonded_book_id', '=', self.bonded_book_id.id),
            ('state', '=', 'active'),
        ])
        for limit in limits:
            if limit.available_value < self.invoice_amount:
                return False
        return True

    def _check_product_filing(self):
        """校验商品备案"""
        for line in self.line_ids:
            filing = self.env['bonded.product'].search([
                ('bonded_book_id', '=', self.bonded_book_id.id),
                ('product_id', '=', line.product_id.id),
                ('state', '=', 'active'),
            ], limit=1)
            if not filing:
                return False
        return True

    def _compute_transit_deadline(self, transport_mode, distance_km=0.0):
        """根据运输方式和距离自动计算transit_deadline"""
        now = fields.Datetime.now()
        base_days = {
            'road': 2,    # base 2 days for 500km
            'sea': 7,
            'air': 3,
            'rail': 5,
        }.get(transport_mode, 7)
        # Road: +1 day per additional 500km
        extra_days = 0
        if transport_mode == 'road' and distance_km > 500:
            extra_days = int((distance_km - 500) / 500) + 1
        total_days = base_days + extra_days
        from datetime import timedelta
        return now + timedelta(days=total_days)

    def _create_gate_arrival_reservation(self):
        """T1审批通过后自动创建到仓登记预约"""
        self.ensure_one()
        self.env['gate.arrival'].create({
            'customs_file_id': self.id,
            'mrn': self.mrn,
            'handover_id': self.handover_id.id if self.handover_id else False,
            'state': 'pending',
        })

    def _create_bonded_inbound(self):
        """B3审批通过后自动创建入库指令"""
        self.ensure_one()
        inbound = self.env['bonded.inbound'].create({
            'bonded_book_id': self.bonded_book_id.id,
            'customs_file_id': self.id,
            'expected_date': fields.Date.today(),
            'total_value': self.invoice_amount,
            'cargo_source': 'port_t1' if self.pre_condition == 't1_closed' else 'direct',
            'state': 'confirmed',  # 自动confirmed
        })
        # 复制商品行
        for line in self.line_ids:
            self.env['bonded.inbound.line'].create({
                'bonded_inbound_id': inbound.id,
                'customs_file_line_id': line.id,
                'product_id': line.product_id.id,
                'planned_qty': line.quantity,
                'uom_id': line.uom_id.id,
            })
        # 关联T1前置MRN(如果有)
        if self.pre_mrn_ids:
            for pre_mrn in self.pre_mrn_ids:
                arrivals = pre_mrn.gate_arrival_ids
                if arrivals:
                    inbound.gate_arrival_ids = [(4, a.id) for a in arrivals]

    def _create_bonded_outbound(self):
        """B3出库审批通过后自动创建出库指令"""
        self.ensure_one()
        outbound_type = {
            'b3_out': 'l2f',
            'ex': 'eu_dispatch',
            'destruction': 'destruction',
        }.get(self.declaration_type, 'l2f')
        self.env['bonded.outbound'].create({
            'bonded_book_id': self.bonded_book_id.id,
            'customs_file_id': self.id,
            'outbound_type': outbound_type,
            'expected_date': fields.Date.today(),
            'total_value': self.invoice_amount,
            'state': 'confirmed',  # 自动confirmed
        })

    def _create_bonded_outbound_t1(self):
        """T1出境审批通过 - 自动创建outbound + 锁定库存(Fix-2)"""
        self.ensure_one()
        outbound = self.env['bonded.outbound'].create({
            'bonded_book_id': self.bonded_book_id.id,
            'customs_file_id': self.id,
            'outbound_type': 't1_transit',
            'mrn': self.mrn,
            'expected_date': fields.Date.today(),
            'total_value': self.invoice_amount,
            'state': 'confirmed',  # 自动confirmed
        })
        # 锁定库存: 在action_confirm中实现

    def _unlock_stock_on_rejection(self):
        """T1出库申报驳回时，一键解锁所有因该申报被锁定的保税库存(Fix-2)"""
        self.ensure_one()
        outbound = self.env['bonded.outbound'].search([
            ('customs_file_id', '=', self.id),
            ('state', '=', 'draft'),
        ], limit=1)
        if outbound:
            outbound.write({'state': 'cancelled'})
        # 解锁库存（由outbound的cancel逻辑处理）
        _logger.info('T1 outbound %s rejected, stock unlock triggered (handled by outbound cancel)', self.mrn)