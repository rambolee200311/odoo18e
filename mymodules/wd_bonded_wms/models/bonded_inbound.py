# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
_logger = logging.getLogger(__name__)


class BondedInbound(models.Model):
    _name = 'bonded.inbound'
    _description = 'Bonded Inbound Instruction'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(string='Inbound No.', required=True, copy=False,
                       default=lambda self: _('New'), readonly=True, index=True)
    bonded_book_id = fields.Many2one('bonded.book', string='Bonded Book', required=True, ondelete='restrict', index=True, domain=[('state', '=', 'active')])
    project_id = fields.Many2one('project.project', string='Project', ondelete='restrict', index=True, tracking=True)
    customs_file_ids = fields.Many2many('bonded.customs.file', 'bonded_inbound_customs_file_rel', 'bonded_inbound_id', 'customs_file_id', string='Customs Declarations', copy=False)

    t1_customs_file_id = fields.Many2one('bonded.customs.file', string='T1 Customs File')
    b3_customs_file_id = fields.Many2one('bonded.customs.file', string='B3 Customs File')


    # 到仓登记 (一个入库单支持多个T1，每条到仓登记只属于一个入库单)
    gate_arrival_ids = fields.One2many('gate.arrival', 'bonded_inbound_id', string='Gate Arrivals',
                                       help='T1 containers arriving at gate. One inbound can consolidate multiple T1 declarations.')
    # 货物来源(F-06)
    cargo_source = fields.Selection([('port_t1', 'Port T1 Import(First Entry)'),
                                     ('eu_bonded_t1', 'EU Bonded T1 Transfer'),
                                     ('direct', 'Direct Entry')], string='Cargo Source', required=True, default='port_t1')
    inbound_tracking_no = fields.Char(string='Inbound Tracking No.', copy=False, index=True)
    expected_date = fields.Date(string='Expected Date', required=True, default=fields.Date.today)
    total_value = fields.Monetary(string='Total Value', compute='_compute_total_value', store=True, readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.ref('base.EUR').id)
    picking_id = fields.Many2one('stock.picking', string='Stock Picking', readonly=True, ondelete='restrict',help='Related warehouse receiving order')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('declared', 'Declared'),
        ('released', 'Released'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True, index=True)
    line_ids = fields.One2many('bonded.inbound.line', 'bonded_inbound_id', string='Products')
    remark = fields.Text(string='Remark')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    warehouse = fields.Many2one('stock.warehouse', string='Warehouse', required=True,
                                default=lambda self: self.env.user.warehouse_id, tracking=True,
                                index=True)
    pick_type = fields.Many2one('stock.picking.type', string='Picking Type', required=True,
                                default=lambda self: self.env.user.warehouse_id.in_type_id,
                                tracking=True, domain=[('code', '=', 'incoming')], index=True)
    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Inbound number must be unique!'),
        ('inbound_tracking_no_uniq', 'unique(inbound_tracking_no)', 'Inbound tracking number must be unique!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('seq.bonded.inbound') or _('New')
        return super().create(vals_list)

    @api.onchange('project_id')
    def onchange_project_id(self):
        for rec in self:
            if rec.project_id:
                rec.warehouse = rec.project_id.warehouse
                rec.pick_type = rec.project_id.inbound_pick_type

    @api.depends('line_ids.subtotal_value')
    def _compute_total_value(self):
        for rec in self:
            rec.total_value = sum(rec.line_ids.mapped('subtotal_value'))

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft inbound instructions can be confirmed.'))
            if not rec.line_ids:
                raise UserError(_('Please add inbound lines before confirming.'))
            rec.bonded_book_id.reserve_document_value(rec.total_value, project_id=rec.project_id.id, inbound_id=rec.id)
            vals = {'state': 'confirmed'}
            if not rec.inbound_tracking_no:
                vals['inbound_tracking_no'] = self.env['ir.sequence'].next_by_code(
                    'seq.bonded.inbound.tracking'
                ) or _('New')
            rec.write(vals)

    @api.constrains('cargo_source', 't1_customs_file_id', 'gate_arrival_ids')
    def check_cargo_source(self):
        for rec in self:
            if rec.cargo_source == 'direct' and (rec.t1_customs_file_id or rec.gate_arrival_ids):
                raise ValidationError(_('Direct entry cannot have T1 customs file or gate arrivals.'))

    @api.constrains('customs_file_ids', 'line_ids.customs_file_line_id')
    def check_customs_file_line_links(self):
        for rec in self:
            selected_lines = rec.line_ids.mapped('customs_file_line_id')
            if not selected_lines:
                continue
            if not rec.customs_file_ids:
                raise ValidationError(_('Select a customs declaration before selecting a declaration line.'))
            if selected_lines.filtered(lambda customs_line: customs_line.customs_file_id not in rec.customs_file_ids):
                raise ValidationError(_('Each declaration line must belong to a customs declaration linked to this inbound instruction.'))

    def action_start(self):
        for rec in self:
            if rec.state != 'released':
                raise UserError(_('Only released inbound instructions can be started.'))


            rec.write({'state': 'in_progress'})

    def action_done(self):
        """指令完成 - 创建bonded.stock + bonded.verification"""
        for rec in self:
            if rec.state != 'in_progress':
                raise UserError(_('Only in-progress instructions can be set to done.'))
            if not rec.picking_id:
                raise UserError(_('Please create and validate a stock picking first.'))
            for move_line in rec.picking_id.move_line_ids:
                inbound_line = move_line.move_id.bonded_inbound_line_id

                if not inbound_line:
                    raise UserError(_('Cannot match stock move line to bonded inbound line.'))
                unit_value = inbound_line.declared_unit_price
                customs_file = inbound_line.customs_file_id
                pre_mrn_ids = [(4, mrn.id) for mrn in customs_file.pre_mrn_ids] if customs_file and customs_file.pre_mrn_ids else False
                bonded_stock = self.env['bonded.stock'].create({
                    'bonded_book_id': rec.bonded_book_id.id,
                    'product_id': move_line.product_id.id,
                    'stock_move_line_id': move_line.id,
                    'lot_id': move_line.lot_id.id if move_line.lot_id else False,
                    'location_id': move_line.location_dest_id.id,
                    'inbound_id': rec.id,
                    'inbound_line_id': inbound_line.id,
                    'inbound_tracking_no': inbound_line.inbound_tracking_no,
                    'customer_batch_no': inbound_line.customer_batch_no,
                    'current_customs_status': 'entrepot',
                    'quantity': move_line.quantity,
                    'unit_value': unit_value,
                    'currency_id': rec.currency_id.id,
                    'inbound_date': fields.Datetime.now(),
                    'gate_arrival_ids': [(4, gate.id) for gate in rec.gate_arrival_ids],
                    'related_t1_in_mrn_ids': pre_mrn_ids,
                })
                self.env['bonded.verification'].create({
                    'bonded_book_id': rec.bonded_book_id.id,
                    'verification_type': 'inbound',
                    'customs_file_id': customs_file.id if customs_file else False,
                    'bonded_stock_id': bonded_stock.id,
                    'from_status': '',
                    'to_status': 'entrepot',
                    'quantity': move_line.quantity,
                    'write_off_value': unit_value * move_line.quantity,
                    'operator_id': self.env.user.id,
                })
                self.env['bonded.book.line'].create({
                    'bonded_book_id': rec.bonded_book_id.id,
                    'date': fields.Date.today(),
                    'operation_type': 'bonded_inbound',
                    'product_id': move_line.product_id.id,
                    'qty_change': move_line.quantity,
                    'to_status': 'entrepot',
                    'direction': 'in',
                    'ref_doc_no': rec.name,
                    'inbound_tracking_no': inbound_line.inbound_tracking_no,
                    'customer_batch_no': inbound_line.customer_batch_no,
                    'bonded_stock_id': bonded_stock.id,
                    'customs_file_id': customs_file.id if customs_file else False,
                    'picking_id': rec.picking_id.id,
                })
            rec.write({'state': 'done'})
            for customs_file in rec.customs_file_ids.filtered(lambda customs_file: customs_file.declaration_type == 'b3_in' and customs_file.state == 'customs_approved'):
                if all(inbound.state == 'done' for inbound in customs_file.inbound_ids):
                    customs_file.write({'state': 'done'})

    def action_cancel(self):
        for rec in self:
            if rec.state not in ('draft', 'confirmed', 'declared'):
                raise UserError(_('Only draft/confirmed/declared inbound instructions can be cancelled.'))
            rec.write({'state': 'cancelled'})

    def unlink(self):
        for rec in self:
            if rec.inbound_tracking_no or rec.customs_file_ids:
                raise UserError(_('Inbound instruction with tracking no. or customs declaration cannot be deleted. Please cancel it instead.'))
        return super().unlink()

    def action_create_picking(self):
        self.ensure_one()
        if self.state != 'released':
            raise UserError(_('Only released instructions can create pickings.'))
        if self.picking_id:
            raise UserError(_('Stock picking already exists.'))
        if not self.warehouse or not self.pick_type:
            raise UserError(_('Please set the warehouse and incoming operation type first.'))
        if self.pick_type.warehouse_id != self.warehouse:
            raise UserError(_('The incoming operation type must belong to the selected warehouse.'))
        if not self.pick_type.default_location_src_id or not self.pick_type.default_location_dest_id:
            raise UserError(_('Please configure source and destination locations on the incoming operation type.'))
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.pick_type.id,
            'location_id': self.pick_type.default_location_src_id.id,
            'location_dest_id': self.pick_type.default_location_dest_id.id,
            'origin': self.name,
            'bonded_inbound_id': self.id,
        })
        for line in self.line_ids:
            self.env['stock.move'].create({
                'name': line.product_id.name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.planned_qty,
                'product_uom': line.uom_id.id or line.product_id.uom_id.id,
                'picking_id': picking.id,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
                'bonded_inbound_line_id': line.id,
            })
        self.write({'picking_id': picking.id, 'state': 'in_progress'})
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
                                           ondelete='set null', index=True)
    customs_file_id = fields.Many2one('bonded.customs.file', related='customs_file_line_id.customs_file_id', string='Customs Declaration', store=True, readonly=True, index=True)
    bonded_product_id = fields.Many2one('bonded.product', string='Bonded Product Filing', ondelete='restrict', index=True)
    product_id = fields.Many2one('product.product', string='Product', required=True, index=True)
    inbound_tracking_no = fields.Char(string='Inbound Tracking No.', related='bonded_inbound_id.inbound_tracking_no', store=True, readonly=True, index=True)
    customer_batch_no = fields.Char(string='Customer Batch No.', copy=False, index=True, required=True)
    planned_qty = fields.Float(string='Planned Qty', required=True, default=1.0)
    declared_unit_price = fields.Monetary(string='Declared Unit Price', required=True, default=0.0)
    subtotal_value = fields.Monetary(string='Subtotal', compute='_compute_subtotal_value', store=True)
    currency_id = fields.Many2one('res.currency', related='bonded_inbound_id.currency_id', string='Currency', readonly=True)
    done_qty = fields.Float(string='Done Qty', compute='_compute_done_qty', store=True)
    uom_id = fields.Many2one('uom.uom', string='UoM', related='product_id.uom_id', readonly=True)
    eligible_product_ids = fields.Many2many('product.product', compute='_compute_eligible_product_ids')
    eligible_bonded_product_ids = fields.Many2many('bonded.product', compute='_compute_eligible_product_ids')
    available_customs_file_line_ids = fields.Many2many('bonded.customs.file.line', compute='_compute_available_customs_file_line_ids')

    @api.model_create_multi
    def create(self, vals_list):
        env_bonded_inbound = self.env['bonded.inbound'].sudo()
        env_bonded_product = self.env['bonded.product'].sudo()
        for vals in vals_list:
            inbound = env_bonded_inbound.browse(vals.get('bonded_inbound_id')).exists()
            if not inbound:
                continue
            filing = env_bonded_product.browse(vals.get('bonded_product_id')).exists()
            if filing:
                vals['product_id'] = filing.product_id.id
            elif vals.get('product_id'):
                filing = env_bonded_product.search([
                    ('bonded_book_id', '=', inbound.bonded_book_id.id),
                    ('product_id', '=', vals['product_id']),
                    ('state', '=', 'active'),
                ], limit=1)
            if filing:
                vals.setdefault('bonded_product_id', filing.id)
                vals.setdefault('declared_unit_price', filing.declared_unit_price)
        return super().create(vals_list)

    @api.onchange('bonded_product_id')
    def onchange_bonded_product_id(self):
        for rec in self:
            if rec.bonded_product_id:
                rec.product_id = rec.bonded_product_id.product_id
                rec.declared_unit_price = rec.bonded_product_id.declared_unit_price

    @api.onchange('product_id')
    def onchange_product_id(self):
        env_bonded_product = self.env['bonded.product'].sudo()
        for rec in self:
            rec.declared_unit_price = 0.0
            if not rec.bonded_inbound_id or not rec.product_id:
                continue
            filing = env_bonded_product.search([
                ('bonded_book_id', '=', rec.bonded_inbound_id.bonded_book_id.id),
                ('product_id', '=', rec.product_id.id),
                ('state', '=', 'active'),
            ], limit=1)
            if filing:
                rec.bonded_product_id = filing
                rec.declared_unit_price = filing.declared_unit_price

    @api.depends('planned_qty', 'declared_unit_price')
    def _compute_subtotal_value(self):
        for rec in self:
            rec.subtotal_value = rec.planned_qty * rec.declared_unit_price

    @api.depends('bonded_inbound_id.bonded_book_id')
    def _compute_eligible_product_ids(self):
        for rec in self:
            book = rec.bonded_inbound_id.bonded_book_id
            filings = self.env['bonded.product'].sudo().search([
                ('bonded_book_id', '=', book.id),
                ('state', '=', 'active'),
            ]) if book else self.env['bonded.product']
            rec.eligible_product_ids = filings.mapped('product_id')
            rec.eligible_bonded_product_ids = filings

    @api.depends('bonded_inbound_id.customs_file_ids', 'bonded_inbound_id.line_ids.customs_file_line_id', 'product_id')
    def _compute_available_customs_file_line_ids(self):
        for rec in self:
            used_lines = (rec.bonded_inbound_id.line_ids - rec).mapped('customs_file_line_id')
            rec.available_customs_file_line_ids = rec.bonded_inbound_id.customs_file_ids.line_ids.filtered(
                lambda customs_line: customs_line.product_id == rec.product_id and customs_line not in used_lines
            )

    @api.constrains('bonded_inbound_id', 'bonded_product_id', 'customs_file_line_id', 'product_id')
    def check_customs_file_line(self):
        for rec in self:
            if rec.bonded_product_id and (rec.bonded_product_id.bonded_book_id != rec.bonded_inbound_id.bonded_book_id or rec.bonded_product_id.product_id != rec.product_id or rec.bonded_product_id.state != 'active'):
                raise ValidationError(_('The bonded product filing must be active and belong to the inbound instruction bonded book.'))
            if not rec.customs_file_line_id:
                continue
            customs_files = rec.bonded_inbound_id.customs_file_ids
            if not customs_files:
                raise ValidationError(_('Select a customs declaration before selecting a declaration line.'))
            if rec.customs_file_line_id.customs_file_id not in customs_files:
                raise ValidationError(_('The declaration line must belong to a customs declaration linked to this inbound instruction.'))
            if rec.customs_file_line_id.product_id != rec.product_id:
                raise ValidationError(_('The declaration line product must match the inbound line product.'))
            duplicate_line = self.sudo().search([
                ('bonded_inbound_id', '=', rec.bonded_inbound_id.id),
                ('customs_file_line_id', '=', rec.customs_file_line_id.id),
                ('id', '!=', rec.id),
            ], limit=1)
            if duplicate_line:
                raise ValidationError(_('A declaration line can only be selected once in an inbound instruction.'))

    @api.constrains('bonded_inbound_id', 'product_id', 'customer_batch_no')
    def check_unique_product_batch(self):
        for rec in self:
            if not rec.bonded_inbound_id or not rec.product_id:
                continue
            domain = [
                ('bonded_inbound_id', '=', rec.bonded_inbound_id.id),
                ('product_id', '=', rec.product_id.id),
                ('customer_batch_no', '=', rec.customer_batch_no or False),
                ('id', '!=', rec.id),
            ]
            if self.sudo().search(domain, limit=1):
                raise ValidationError(_('The same product and customer batch cannot be repeated in one inbound instruction.'))

    @api.depends('bonded_inbound_id.picking_id.move_ids.state', 'bonded_inbound_id.picking_id.move_ids.product_uom_qty')
    def _compute_done_qty(self):
        for rec in self:
            if rec.bonded_inbound_id.picking_id:
                moves = rec.bonded_inbound_id.picking_id.move_ids.filtered(
                    lambda move: move.bonded_inbound_line_id == rec and move.state == 'done'
                )
                rec.done_qty = sum(moves.mapped('product_uom_qty'))
            else:
                rec.done_qty = 0.0
