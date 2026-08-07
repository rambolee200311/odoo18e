# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class TransportDGD(models.Model):
    _name = 'tlmp.transport.dgd'
    _description = 'DGD - Dangerous Goods Declaration (ADR Compliance)'
    _rec_name = 'name'
    _order = 'id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ── Identification ──────────────────────────────────────
    name = fields.Char(string='Reference', required=True, copy=False,
                       default=lambda self: _('New'))
    order_id = fields.Many2one('tlmp.transport.order', string='Transport Order',
                               required=True, index=True, ondelete='cascade')
    # Reserved for future CMR-DGD linkage
    cmr_id = fields.Many2one('tlmp.cmr', string='Related CMR',
                             readonly=True, copy=False,
                             help='Reserved for future CMR-DGD document linkage.')

    # ── Six-State Lifecycle ─────────────────────────────────
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('generated', 'Generated'),
        ('signed', 'Signed'),
        ('archived', 'Archived'),
        ('void', 'Void'),
    ], string='Status', default='draft', tracking=True,
       help=('Draft Confirmed Generated Signed Archived Void'))

    # ── Lines (Snapshot from cargo_line) ────────────────────
    dgd_line_ids = fields.One2many('tlmp.transport.dgd.line', 'dgd_id',
                                   string='DGD Cargo Lines', copy=True)

    # ── Snapshot totals from lines ──────────────────────────
    total_packages = fields.Integer(string='Total Packages',
                                    compute='_compute_from_lines', store=True)
    total_gross_weight = fields.Float(string='Total Gross Weight (kg)',
                                      compute='_compute_from_lines', store=True)
    total_net_weight = fields.Float(string='Total Net Weight (kg)',
                                    compute='_compute_from_lines', store=True)

    # ── Void Audit ──────────────────────────────────────────
    void_reason = fields.Text(string='Void Reason', copy=False)
    void_date = fields.Datetime(string='Void Date', copy=False, readonly=True)
    void_uid = fields.Many2one('res.users', string='Voided By', copy=False, readonly=True)
    void_log_ids = fields.One2many('tlmp.transport.dgd.void.log', 'dgd_id',
                                   string='Void Logs', readonly=True)

    # ── Compliance Officer tracking ─────────────────────────
    confirmed_uid = fields.Many2one('res.users', string='Confirmed By', readonly=True, copy=False)
    confirmed_date = fields.Datetime(string='Confirmed Date', readonly=True, copy=False)
    signed_uid = fields.Many2one('res.users', string='Signed By', readonly=True, copy=False)
    signed_date = fields.Datetime(string='Signed Date', readonly=True, copy=False)

    # ── Computed totals ─────────────────────────────────────
    @api.depends('dgd_line_ids.packages', 'dgd_line_ids.gross_weight', 'dgd_line_ids.net_weight')
    def _compute_from_lines(self):
        for dgd in self:
            lines = dgd.dgd_line_ids
            dgd.total_packages = sum(lines.mapped('packages') or [0])
            dgd.total_gross_weight = sum(lines.mapped('gross_weight') or [0.0])
            dgd.total_net_weight = sum(lines.mapped('net_weight') or [0.0])

    # ── SQL constraints ─────────────────────────────────────
    _sql_constraints = [
        ('dgd_order_unique', 'UNIQUE(order_id, state)',
         _('Only one DGD per order per state is allowed.')),
    ]

    # ── Auto-sequence ───────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('tlmp.dgd.seq') or _('New')
        return super().create(vals_list)

    # ── State transition actions ────────────────────────────
    def action_confirm(self):
        for r in self:
            if r.state != 'draft':
                raise UserError(_('Only draft DGD can be confirmed.'))
        self.write({
            'state': 'confirmed',
            'confirmed_uid': self.env.uid,
            'confirmed_date': fields.Datetime.now(),
        })

    def action_generate(self):
        for r in self:
            if r.state != 'confirmed':
                raise UserError(_('Only confirmed DGD can be generated.'))
        self.write({'state': 'generated'})

    def action_sign(self):
        for r in self:
            if r.state != 'generated':
                raise UserError(_('Only generated DGD can be signed.'))
            if not r.dgd_line_ids:
                raise UserError(_('Cannot sign DGD with no cargo lines.'))
        self.write({
            'state': 'signed',
            'signed_uid': self.env.uid,
            'signed_date': fields.Datetime.now(),
        })

    def action_archive(self):
        for r in self:
            if r.state not in ('signed', 'archived'):
                raise UserError(_('Only signed DGD can be archived.'))
        self.write({'state': 'archived'})

    def action_void(self):
        for r in self:
            if r.state in ('void',):
                raise UserError(_('DGD is already void.'))
        VoidLog = self.env['tlmp.transport.dgd.void.log']
        for r in self:
            if not r.void_reason:
                raise UserError(_('Void reason is required.'))
            self.env['tlmp.transport.dgd.void.log'].create({
                'dgd_id': r.id,
                'void_reason': r.void_reason,
                'void_uid': self.env.uid,
                'void_date': fields.Datetime.now(),
            })
        self.write({
            'state': 'void',
            'void_date': fields.Datetime.now(),
            'void_uid': self.env.uid,
        })

    # ── Prefill from cargo_line ─────────────────────────────
    def action_prefill_from_cargo(self):
        """Create DGD lines from order cargo_line snapshot."""
        self.ensure_one()
        if self.dgd_line_ids:
            raise UserError(_('DGD already has cargo lines. Clear first or create new DGD.'))
        order = self.order_id
        if not order:
            raise UserError(_('No transport order linked.'))
        DGLine = self.env['tlmp.transport.dgd.line']
        for cl in order.cargo_line_ids:
            DGLine.create({
                'dgd_id': self.id,
                'source_cargo_line_id': cl.id,
                'dangerous_goods_profile_id': cl.dangerous_goods_profile_id.id,
                'commodity': cl.description or cl.commodity or '',
                'packages': cl.packages or 0,
                'gross_weight': cl.gross_weight or 0.0,
                'net_weight': cl.net_weight or 0.0,
                'volume_m3': cl.volume_m3 or 0.0,
                'container_no': cl.container_no or '',
                'is_snapshot': True,
            })
        return True


class TransportDGDLine(models.Model):
    _name = 'tlmp.transport.dgd.line'
    _description = 'DGD Cargo Line - Snapshot from cargo_line'
    _order = 'sequence, id'

    dgd_id = fields.Many2one('tlmp.transport.dgd', string='DGD',
                             required=True, index=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)

    # Source reference
    source_cargo_line_id = fields.Many2one('tlmp.transport.cargo.line',
                                           string='Source Cargo Line',
                                           readonly=True, index=True)
    dangerous_goods_profile_id = fields.Many2one(
        'tlmp.transport.dangerous.goods.profile',
        string='Dangerous Goods Profile', readonly=True)

    # Snapshot fields (copied from cargo_line at generation time)
    commodity = fields.Char(string='Commodity', required=True)
    packages = fields.Integer(string='Packages')
    gross_weight = fields.Float(string='Gross Weight (kg)')
    net_weight = fields.Float(string='Net Weight (kg)')
    volume_m3 = fields.Float(string='Volume (m3)')
    container_no = fields.Char(string='Container No.')

    # ADR snapshot fields (from dangerous_goods_profile UN dictionary)
    un_number = fields.Char(string='UN Number')
    proper_shipping_name = fields.Char(string='Proper Shipping Name')
    hazard_class = fields.Char(string='Class')
    classification_code = fields.Char(string='Classification Code')
    packing_group = fields.Selection([
        ('I', 'I'),
        ('II', 'II'),
        ('III', 'III'),
        ('none', 'N/A'),
    ], string='Packing Group', default='none')
    tunnel_code = fields.Char(string='Tunnel Code')
    transport_category = fields.Char(string='Transport Category')
    special_provision = fields.Char(string='Special Provision')

    # Snapshot marker
    is_snapshot = fields.Boolean(string='Is Snapshot', default=True, readonly=True)

    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('check_net_weight_le_gross',
         'CHECK(net_weight <= gross_weight + 0.01)',
         _('Net weight must not exceed gross weight.')),
    ]

    @api.constrains('gross_weight', 'net_weight')
    def _check_weights(self):
        for r in self:
            if r.gross_weight and r.net_weight and r.net_weight > r.gross_weight:
                raise ValidationError(_(
                    'Net weight (%.2f kg) cannot exceed gross weight (%.2f kg).'
                ) % (r.net_weight, r.gross_weight))

    @api.constrains('tunnel_code')
    def _check_tunnel_code(self):
        valid = ('A', 'B', 'C', 'D', 'E', '')
        for r in self:
            if r.tunnel_code and r.tunnel_code.upper() not in valid:
                raise ValidationError(_(
                    'Tunnel code must be one of: A, B, C, D, E, or empty.'
                ))


class TransportDGDVoidLog(models.Model):
    _name = 'tlmp.transport.dgd.void.log'
    _description = 'DGD Void Audit Log'
    _order = 'id desc'
    _rec_name = 'dgd_id'

    dgd_id = fields.Many2one('tlmp.transport.dgd', string='DGD',
                             required=True, index=True, ondelete='cascade')
    void_reason = fields.Text(string='Void Reason', required=True)
    void_uid = fields.Many2one('res.users', string='Voided By',
                               required=True, default=lambda self: self.env.uid)
    void_date = fields.Datetime(string='Void Date', required=True,
                                default=fields.Datetime.now)
    order_name = fields.Char(string='Order Reference',
                             related='dgd_id.order_id.name', store=True)
    dgd_name = fields.Char(string='DGD Reference',
                           related='dgd_id.name', store=True)
