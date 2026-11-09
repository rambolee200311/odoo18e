# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare
_logger = logging.getLogger(__name__)


class BondedInbound(models.Model):
    _name = 'bonded.inbound'
    _description = 'Bonded Inbound Instruction'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(string='Inbound No.', required=True, copy=False,
                       default=lambda self: _('New'), readonly=True, index=True)
    order_type = fields.Selection([('inbound', 'Inbound')], string='Order Type', required=True, default='inbound', tracking=True, index=True)
    customs_file_state = fields.Selection(related='inbound_tracking_id.customs_file_id.state', string='Customs File Status', readonly=True, store=True, index=True)
    reference = fields.Char(string='Reference', copy=False, index=True, tracking=True)
    order_date = fields.Date(string='Order Date', required=True, default=fields.Date.today, tracking=True, index=True)
    bonded_book_id = fields.Many2one('bonded.book', string='Bonded Book', required=True, ondelete='restrict', index=True, domain=[('state', '=', 'active')], tracking=True)
    project_id = fields.Many2one('project.project', string='Project', required=True, ondelete='restrict', index=True, tracking=True)
    owner_id = fields.Many2one('res.partner', related='project_id.owner', string='Owner', store=True, readonly=True, index=True)
    bl_no = fields.Char(string='Bill of Lading No.', index=True, tracking=True)
    cntr_no = fields.Char(string='Container No.', index=True, tracking=True)
    is_dangerous = fields.Boolean(string='Dangerous Goods', default=False, tracking=True)
    package_generation_mode = fields.Selection(related='project_id.package_generation_mode', string='Package Generation Mode', readonly=True)
    t1_customs_file_ids = fields.One2many('bonded.customs.file', 'bonded_inbound_id', string='T1 Customs Declarations', tracking=True)
    t1_is_closed = fields.Boolean(string='T1 Closed', compute='_compute_t1_is_closed', store=True)
    t1_closed_date = fields.Datetime(related='inbound_tracking_id.customs_file_id.t1_closed_date', string='T1 Closed Date', store=True, readonly=True, index=True)
    mrn = fields.Char(related='inbound_tracking_id.mrn', string='MRN', store=True, readonly=True, index=True)
    mrn_status = fields.Selection(related='inbound_tracking_id.mrn_id.state', string='MRN Status', store=True, readonly=True, index=True)
    gate_arrival_ids = fields.One2many('gate.arrival', 'bonded_inbound_id', string='Gate Arrival', help='One T1 gate arrival is currently allowed for each inbound instruction.', tracking=True)
    inbound_tracking_id = fields.Many2one('bonded.inbound.tracking', string='Unique Identifier No.', readonly=True, copy=False, ondelete='restrict', index=True, tracking=True)
    expected_date = fields.Date(string='Expected Date', required=True, default=fields.Date.today, tracking=True)
    actual_inbound_date = fields.Date(string='Actual Inbound Date (Manual)', copy=False, index=True, tracking=True)
    total_value = fields.Monetary(string='Total Value', compute='_compute_total_value', store=True, readonly=True, tracking=True)
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.ref('base.EUR').id, tracking=True)
    picking_id = fields.Many2one('stock.picking', string='Stock Picking', readonly=True, ondelete='restrict',help='Related warehouse receiving order', tracking=True)
    picking_status = fields.Selection(related='picking_id.state', string='Inbound Picking Status', store=True, readonly=True, index=True)
    picking_validation_time = fields.Datetime(related='picking_id.date_done', string='Inbound Picking Validation Time', readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('declared', 'Declared'),
        ('released', 'Released'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True, index=True)
    line_ids = fields.One2many('bonded.inbound.line', 'bonded_inbound_id', string='Products', tracking=True)
    remark = fields.Text(string='Remark', tracking=True)
    confirm_user_id = fields.Many2one('res.users', string='Confirmed By', readonly=True, copy=False, index=True, tracking=True)
    confirm_time_user_tz = fields.Datetime(string='Confirm Time (User Timezone)', readonly=True, copy=False, tracking=True)
    confirm_time_server = fields.Datetime(string='Confirm Time (Server)', readonly=True, copy=False, tracking=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    warehouse = fields.Many2one('stock.warehouse', string='Warehouse', required=True,
                                default=lambda self: self.env.user.warehouse_id, tracking=True,
                                index=True)
    warehouse_address = fields.Char(related='warehouse.partner_id.contact_address', string='Warehouse Address', readonly=True)
    pick_type = fields.Many2one('stock.picking.type', string='Picking Type', required=True,
                                default=lambda self: self.env.user.warehouse_id.in_type_id,
                                tracking=True, domain=[('code', '=', 'incoming')], index=True)
    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Inbound number must be unique!'),
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

    @api.depends('t1_customs_file_ids.state')
    def _compute_t1_is_closed(self):
        for rec in self:
            rec.t1_is_closed = bool(rec.t1_customs_file_ids) and all(customs_file.state == 'done' for customs_file in rec.t1_customs_file_ids)

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft inbound instructions can be confirmed.'))
            if not rec.line_ids:
                raise UserError(_('Please add inbound lines before confirming.'))
            rec.check_pallet_no()
            rec.bonded_book_id.reserve_document_value(rec.total_value, project_id=rec.project_id.id, inbound_id=rec.id)
            now = fields.Datetime.now()
            vals = {'state': 'confirmed', 'confirm_user_id': self.env.user.id, 'confirm_time_user_tz': fields.Datetime.to_string(fields.Datetime.context_timestamp(rec, now)), 'confirm_time_server': now}
            if not rec.inbound_tracking_id:
                tracking = self.env['bonded.inbound.tracking'].create({'name': self.env['ir.sequence'].next_by_code('seq.bonded.inbound.tracking') or _('New'), 'bonded_inbound_id': rec.id, 'customs_file_id': rec.t1_customs_file_ids[:1].id})
                vals['inbound_tracking_id'] = tracking.id
            rec.write(vals)

    def check_pallet_no(self):
        for rec in self:
            if rec.package_generation_mode in ('inbound', 'picking') and rec.line_ids.filtered(lambda line: not line.pallet_no):
                raise UserError(_('Pallet Number is required for each inbound line when Package Generation Mode is Inbound or Picking.'))

    def action_generate_packages(self):
        for rec in self:
            if rec.package_generation_mode != 'inbound':
                raise UserError(_('Packages can only be generated with this button when Package Generation Mode is Inbound.'))
            if rec.state not in ('confirmed', 'declared', 'released') or rec.picking_id:
                raise UserError(_('Packages can only be generated before creating the picking for a confirmed inbound instruction.'))
            if not rec.line_ids:
                raise UserError(_('Please add inbound lines before generating packages.'))
            rec.check_pallet_no()
            pallet_packages = {}
            package_name_prefix = '-'.join(part for part in (rec.project_id.name, rec.name) if part)
            for line in rec.line_ids.filtered('package_id'):
                package = pallet_packages.get(line.pallet_no)
                if package and package != line.package_id:
                    raise UserError(_('Lines with pallet number %s must use the same package.') % line.pallet_no)
                pallet_packages[line.pallet_no] = line.package_id
            for line in rec.line_ids.filtered(lambda item: not item.package_id):
                package = pallet_packages.get(line.pallet_no)
                if not package:
                    package = self.env['stock.quant.package'].create({'name': '%s-%s' % (package_name_prefix, line.pallet_no), 'package_use': 'disposable'})
                    pallet_packages[line.pallet_no] = package
                line.write({'package_id': package.id})

    def action_create_t1_in_customs_file(self):
        customs_file = self.env['bonded.customs.file']
        for rec in self:
            if rec.state not in ('confirmed', 'declared'):
                raise UserError(_('Only confirmed or declared inbound instructions can create a T1 inbound declaration.'))
            active_customs_files = rec.t1_customs_file_ids.filtered(lambda item: item.state != 'cancelled')
            if active_customs_files:
                raise UserError(_('This inbound instruction already has an active T1 declaration. Return a rejected file to draft and edit it, or cancel the existing file before creating another.'))
            env_bonded_value_ledger = self.env['bonded.value.ledger'].sudo()
            value_ledger = env_bonded_value_ledger.search([('bonded_book_id', '=', rec.bonded_book_id.id), ('inbound_id', '=', rec.id)])
            if not sum(value_ledger.mapped('reserved_change')) and not sum(value_ledger.mapped('deducted_change')):
                rec.bonded_book_id.reserve_document_value(rec.total_value, project_id=rec.project_id.id, inbound_id=rec.id)
            eori_entity = rec.bonded_book_id.eori_entity_id
            line_vals = []
            for item_no, line in enumerate(rec.line_ids, 1):
                line_vals.append((0, 0, {
                    'item_no': item_no,
                    'bonded_product_id': line.bonded_product_id.id,
                    'product_id': line.product_id.id,
                    'origin_country_id': eori_entity.country_id.id,
                    'quantity': line.planned_qty,
                    'gross_weight': line.planned_qty * line.gross_weight,
                    'net_weight': line.planned_qty * line.net_weight,
                    'line_value': line.subtotal_value,
                    'currency_id': rec.currency_id.id,
                }))
            customs_file = self.env['bonded.customs.file'].create({
                'bonded_book_id': rec.bonded_book_id.id,
                'bonded_inbound_id': rec.id,
                'declaration_type': 't1_in',
                'customs_code': rec.bonded_book_id.customs_office_code,
                'consignor_eori_entity_id': eori_entity.id,
                'consignee_eori_entity_id': eori_entity.id,
                'declarant_eori_entity_id': eori_entity.id,
                'origin_country_id': eori_entity.country_id.id,
                'destination_country_id': eori_entity.country_id.id,
                'total_packages': sum(rec.line_ids.mapped('planned_qty')),
                'total_gross_weight': sum(line.planned_qty * line.gross_weight for line in rec.line_ids),
                'invoice_amount': rec.total_value,
                'currency_id': rec.currency_id.id,
                'line_ids': line_vals,
            })
            if rec.inbound_tracking_id and (not rec.inbound_tracking_id.customs_file_id or rec.inbound_tracking_id.customs_file_id.state in ('customs_rejected', 'cancelled')):
                rec.inbound_tracking_id.write({'customs_file_id': customs_file.id})
        return {'type': 'ir.actions.act_window', 'res_model': 'bonded.customs.file', 'res_id': customs_file.id, 'view_mode': 'form', 'target': 'current'}

    @api.constrains('t1_customs_file_ids')
    def check_t1_inbound_links(self):
        for rec in self:
            if rec.t1_customs_file_ids.filtered(lambda customs_file: customs_file.declaration_type != 't1_in'):
                raise ValidationError(_('Inbound instructions must be linked to T1 customs declarations.'))
            if rec.t1_customs_file_ids.filtered(lambda customs_file: customs_file.bonded_book_id != rec.bonded_book_id):
                raise ValidationError(_('T1 customs declarations and the inbound instruction must use the same bonded book.'))

    @api.constrains('t1_customs_file_ids', 'line_ids.customs_file_line_id')
    def check_customs_file_line_links(self):
        for rec in self:
            selected_lines = rec.line_ids.mapped('customs_file_line_id')
            if not selected_lines:
                continue
            if selected_lines.filtered(lambda customs_line: customs_line.customs_file_id not in rec.t1_customs_file_ids):
                raise ValidationError(_('Each declaration line must belong to a T1 customs declaration linked to this inbound instruction.'))

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
            if not rec.picking_id or rec.picking_id.state != 'done':
                raise UserError(_('Please validate the linked stock picking before completing the inbound instruction.'))
            for move_line in rec.picking_id.move_line_ids:
                inbound_line = move_line.move_id.bonded_inbound_line_id

                if not inbound_line:
                    raise UserError(_('Cannot match stock move line to bonded inbound line.'))
                unit_value = inbound_line.declared_unit_price
                customs_file = inbound_line.customs_file_line_id.customs_file_id or rec.t1_customs_file_ids[:1]
                bonded_stock = self.env['bonded.stock'].create({
                    'bonded_book_id': rec.bonded_book_id.id,
                    'product_id': move_line.product_id.id,
                    'stock_move_line_id': move_line.id,
                    'lot_id': move_line.lot_id.id if move_line.lot_id else False,
                    'location_id': move_line.location_dest_id.id,
                    'inbound_id': rec.id,
                    'inbound_line_id': inbound_line.id,
                    'inbound_tracking_no': inbound_line.inbound_tracking_no,
                    'current_customs_status': 'entrepot',
                    'quantity': move_line.quantity,
                    'unit_value': unit_value,
                    'currency_id': rec.currency_id.id,
                    'inbound_date': fields.Datetime.now(),
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
                    'bonded_stock_id': bonded_stock.id,
                    'customs_file_id': customs_file.id if customs_file else False,
                    'picking_id': rec.picking_id.id,
                })
            rec.write({'state': 'done'})

    def action_cancel(self):
        for rec in self:
            if rec.state not in ('draft', 'confirmed', 'declared'):
                raise UserError(_('Only draft/confirmed/declared inbound instructions can be cancelled.'))
            active_customs_files = rec.t1_customs_file_ids.filtered(lambda item: item.state != 'cancelled')
            if active_customs_files:
                raise UserError(_('Cancel the active T1 declaration before cancelling this inbound instruction.'))
            rec.bonded_book_id.release_document_value(project_id=rec.project_id.id, inbound_id=rec.id)
            rec.write({'state': 'cancelled'})

    def action_return_to_draft(self):
        for rec in self:
            if rec.state != 'confirmed' or rec.t1_customs_file_ids:
                raise UserError(_('Only confirmed inbound instructions without a T1 customs declaration can be returned to draft.'))
            rec.bonded_book_id.release_document_value(project_id=rec.project_id.id, inbound_id=rec.id)
            rec.write({'state': 'draft', 'confirm_user_id': False, 'confirm_time_user_tz': False, 'confirm_time_server': False})

    def unlink(self):
        for rec in self:
            if rec.inbound_tracking_id or rec.t1_customs_file_ids:
                raise UserError(_('Inbound instruction with tracking no. or customs declaration cannot be deleted. Please cancel it instead.'))
        return super().unlink()

    def action_create_picking(self):
        picking = self.env['stock.picking']
        env_stock_lot = self.env['stock.lot'].sudo()
        env_stock_move_line = self.env['stock.move.line']
        env_traceability_line = self.env['bonded.inbound.traceability.line'].sudo()
        for rec in self:
            if rec.state != 'released':
                raise UserError(_('Only released instructions can create pickings.'))
            active_customs_files = rec.t1_customs_file_ids.filtered(lambda customs_file: customs_file.state not in ('customs_rejected', 'cancelled'))
            if not active_customs_files or active_customs_files.filtered(lambda customs_file: customs_file.state != 'done'):
                raise UserError(_('All active T1 inbound declarations must be closed before creating a stock picking.'))
            if rec.picking_id:
                raise UserError(_('Stock picking already exists.'))
            if not rec.warehouse or not rec.pick_type:
                raise UserError(_('Please set the warehouse and incoming operation type first.'))
            if rec.pick_type.warehouse_id != rec.warehouse:
                raise UserError(_('The incoming operation type must belong to the selected warehouse.'))
            if not rec.pick_type.default_location_src_id or not rec.pick_type.default_location_dest_id:
                raise UserError(_('Please configure source and destination locations on the incoming operation type.'))
            rec.check_pallet_no()
            pallet_packages = {}
            package_name_prefix = '-'.join(part for part in (rec.project_id.name, rec.name) if part)
            if rec.package_generation_mode in ('inbound', 'picking'):
                for line in rec.line_ids.filtered('package_id'):
                    package = pallet_packages.get(line.pallet_no)
                    if package and package != line.package_id:
                        raise UserError(_('Lines with pallet number %s must use the same package.') % line.pallet_no)
                    pallet_packages[line.pallet_no] = line.package_id
                if rec.package_generation_mode == 'inbound':
                    if rec.line_ids.filtered(lambda line: not line.package_id):
                        raise UserError(_('Please use Create Packages before creating the picking.'))
            picking = self.env['stock.picking'].create({
                'picking_type_id': rec.pick_type.id,
                'location_id': rec.pick_type.default_location_src_id.id,
                'location_dest_id': rec.pick_type.default_location_dest_id.id,
                'origin': rec.name,
                'bonded_inbound_id': rec.id,
                'unique_identifier_no': rec.inbound_tracking_id.name,
                'bonded_customs_file_id': (rec.inbound_tracking_id.customs_file_id or rec.t1_customs_file_ids[:1]).id,
            })
            if rec.package_generation_mode == 'picking':
                for line in rec.line_ids.filtered(lambda line: not line.package_id):
                    package = pallet_packages.get(line.pallet_no)
                    if not package:
                        package = self.env['stock.quant.package'].create({'name': '%s-%s' % (package_name_prefix, line.pallet_no), 'package_use': 'disposable'})
                        pallet_packages[line.pallet_no] = package
                    line.write({'package_id': package.id})
            for line in rec.line_ids:
                move = self.env['stock.move'].create({
                    'name': line.product_id.name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.planned_qty,
                    'product_uom': line.uom_id.id or line.product_id.uom_id.id,
                    'picking_id': picking.id,
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                    'bonded_inbound_line_id': line.id,
                })
                traceability_lines = env_traceability_line.search([('inbound_line_id', '=', line.id)])
                if traceability_lines:
                    total_qty = sum(traceability_lines.mapped('planned_qty'))
                    if float_compare(total_qty, line.planned_qty, precision_rounding=(line.uom_id or line.product_id.uom_id).rounding) != 0:
                        raise UserError(_('The total lot/SN planned quantity must equal the inbound product line quantity.'))
                    for traceability_line in traceability_lines:
                        lot = env_stock_lot.search([
                            ('name', '=', traceability_line.lot_name),
                            ('product_id', '=', traceability_line.product_id.id),
                        ], limit=1)
                        if not lot:
                            lot = self.env['stock.lot'].create({'name': traceability_line.lot_name, 'product_id': traceability_line.product_id.id})
                        move_line_vals = {
                            'picking_id': picking.id,
                            'move_id': move.id,
                            'product_id': line.product_id.id,
                            'product_uom_id': line.uom_id.id or line.product_id.uom_id.id,
                            'quantity': traceability_line.planned_qty,
                            'location_id': picking.location_id.id,
                            'location_dest_id': picking.location_dest_id.id,
                            'lot_id': lot.id,
                        }
                        if line.package_id:
                            move_line_vals['result_package_id'] = line.package_id.id
                        env_stock_move_line.create(move_line_vals)
                else:
                    move_line_vals = {
                        'picking_id': picking.id,
                        'move_id': move.id,
                        'product_id': line.product_id.id,
                        'product_uom_id': line.uom_id.id or line.product_id.uom_id.id,
                        'quantity': line.planned_qty,
                        'location_id': picking.location_id.id,
                        'location_dest_id': picking.location_dest_id.id,
                    }
                    if line.package_id:
                        move_line_vals['result_package_id'] = line.package_id.id
                    if line.product_id.tracking == 'serial':
                        for index in range(int(line.planned_qty)):
                            env_stock_move_line.create(dict(move_line_vals, quantity=1.0))
                    else:
                        env_stock_move_line.create(move_line_vals)
            rec.write({'picking_id': picking.id, 'state': 'in_progress'})
        return {'type': 'ir.actions.client', 'tag': 'reload'}


class BondedInboundLine(models.Model):
    _name = 'bonded.inbound.line'
    _description = 'Bonded Inbound Line'
    _order = 'bonded_inbound_id, pallet_no, id'

    bonded_inbound_id = fields.Many2one('bonded.inbound', string='Inbound Instruction',
                                        required=True, ondelete='cascade', index=True)
    customs_file_line_id = fields.Many2one('bonded.customs.file.line', string='Declaration Line',
                                           ondelete='set null', index=True)
    customs_file_id = fields.Many2one('bonded.customs.file', related='customs_file_line_id.customs_file_id', string='Customs Declaration', store=True, readonly=True, index=True)
    bonded_product_id = fields.Many2one('bonded.product', string='Bonded Product Filing', ondelete='restrict', index=True)
    product_id = fields.Many2one('product.product', string='Product', required=True, index=True)
    inbound_tracking_no = fields.Char(string='Unique Identifier No.', related='bonded_inbound_id.inbound_tracking_id.name', store=True, readonly=True, index=True)
    traceability_line_ids = fields.One2many('bonded.inbound.traceability.line', 'inbound_line_id', string='Lot/SN Details', copy=False)
    traceability_tag_line_ids = fields.Many2many('bonded.inbound.traceability.line', string='Lot/SN', compute='_compute_traceability_tag_line_ids', inverse='_inverse_traceability_tag_line_ids', readonly=False)
    pallet_no = fields.Char(string='Pallet Number', index=True)
    package_id = fields.Many2one('stock.quant.package', string='Package', ondelete='restrict', index=True)
    planned_qty = fields.Float(string='Planned Qty', required=True, default=1.0)
    declared_unit_price = fields.Monetary(string='Declared Unit Price', required=True, default=0.0)
    gross_weight = fields.Float(string='Gross Weight (kg)')
    net_weight = fields.Float(string='Net Weight (kg)')
    product_tracking = fields.Selection(related='product_id.tracking', string='Tracking', readonly=True)
    subtotal_value = fields.Monetary(string='Subtotal', compute='_compute_subtotal_value', store=True)
    currency_id = fields.Many2one('res.currency', related='bonded_inbound_id.currency_id', string='Currency', readonly=True)
    done_qty = fields.Float(string='Done Qty', compute='_compute_done_qty', store=True)
    uom_id = fields.Many2one('uom.uom', string='UoM', related='bonded_product_id.uom_id', readonly=True)
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
                    ('categ_id', '=', inbound.project_id.category.id),
                    ('state', '=', 'active'),
                ], limit=1)
            if filing:
                vals.setdefault('bonded_product_id', filing.id)
                vals.setdefault('declared_unit_price', filing.declared_unit_price)
                vals.setdefault('gross_weight', filing.gross_weight)
                vals.setdefault('net_weight', filing.net_weight)
        return super().create(vals_list)

    @api.onchange('bonded_product_id')
    def onchange_bonded_product_id(self):
        for rec in self:
            if rec.bonded_product_id:
                rec.product_id = rec.bonded_product_id.product_id
                rec.declared_unit_price = rec.bonded_product_id.declared_unit_price
                rec.gross_weight = rec.bonded_product_id.gross_weight
                rec.net_weight = rec.bonded_product_id.net_weight

    @api.onchange('product_id')
    def onchange_product_id(self):
        env_bonded_product = self.env['bonded.product'].sudo()
        for rec in self:
            rec.declared_unit_price = 0.0
            rec.gross_weight = 0.0
            rec.net_weight = 0.0
            if not rec.bonded_inbound_id or not rec.product_id:
                continue
            filing = env_bonded_product.search([
                ('bonded_book_id', '=', rec.bonded_inbound_id.bonded_book_id.id),
                ('product_id', '=', rec.product_id.id),
                ('categ_id', '=', rec.bonded_inbound_id.project_id.category.id),
                ('state', '=', 'active'),
            ], limit=1)
            if filing:
                rec.bonded_product_id = filing
                rec.declared_unit_price = filing.declared_unit_price
                rec.gross_weight = filing.gross_weight
                rec.net_weight = filing.net_weight

    @api.constrains('product_id', 'planned_qty')
    def check_serial_planned_qty(self):
        for rec in self:
            if rec.product_id.tracking == 'serial' and rec.planned_qty != int(rec.planned_qty):
                raise ValidationError(_('The planned quantity of a serial-tracked product must be an integer.'))

    @api.depends('traceability_line_ids')
    def _compute_traceability_tag_line_ids(self):
        for rec in self:
            rec.traceability_tag_line_ids = rec.traceability_line_ids

    def _inverse_traceability_tag_line_ids(self):
        for rec in self:
            (rec.traceability_line_ids - rec.traceability_tag_line_ids).unlink()
            for traceability_line in rec.traceability_tag_line_ids - rec.traceability_line_ids:
                traceability_line.write({'inbound_line_id': rec.id, 'product_id': rec.product_id.id})

    @api.depends('planned_qty', 'declared_unit_price')
    def _compute_subtotal_value(self):
        for rec in self:
            rec.subtotal_value = rec.planned_qty * rec.declared_unit_price

    @api.depends('bonded_inbound_id.bonded_book_id', 'bonded_inbound_id.project_id.category')
    def _compute_eligible_product_ids(self):
        for rec in self:
            book = rec.bonded_inbound_id.bonded_book_id
            category = rec.bonded_inbound_id.project_id.category
            filings = self.env['bonded.product'].sudo().search([
                ('bonded_book_id', '=', book.id),
                ('categ_id', '=', category.id),
                ('state', '=', 'active'),
            ]) if book and category else self.env['bonded.product']
            rec.eligible_product_ids = filings.mapped('product_id')
            rec.eligible_bonded_product_ids = filings

    @api.depends('bonded_inbound_id.t1_customs_file_ids.line_ids', 'bonded_inbound_id.line_ids.customs_file_line_id', 'product_id')
    def _compute_available_customs_file_line_ids(self):
        for rec in self:
            used_lines = (rec.bonded_inbound_id.line_ids - rec).mapped('customs_file_line_id')
            declaration_lines = rec.bonded_inbound_id.t1_customs_file_ids.mapped('line_ids')
            rec.available_customs_file_line_ids = declaration_lines.filtered(
                lambda customs_line: customs_line.product_id == rec.product_id and customs_line not in used_lines
            )

    @api.constrains('bonded_inbound_id', 'bonded_product_id', 'customs_file_line_id', 'product_id')
    def check_customs_file_line(self):
        for rec in self:
            if rec.bonded_product_id and (rec.bonded_product_id.bonded_book_id != rec.bonded_inbound_id.bonded_book_id or rec.bonded_product_id.product_id != rec.product_id or rec.bonded_product_id.categ_id != rec.bonded_inbound_id.project_id.category or rec.bonded_product_id.state != 'active'):
                raise ValidationError(_('The bonded product filing must be active and belong to the inbound instruction bonded book and project product category.'))
            if not rec.customs_file_line_id:
                continue
            if rec.customs_file_line_id.customs_file_id not in rec.bonded_inbound_id.t1_customs_file_ids:
                raise ValidationError(_('The declaration line must belong to a T1 customs declaration linked to the inbound instruction.'))
            if rec.customs_file_line_id.product_id != rec.product_id:
                raise ValidationError(_('The declaration line product must match the inbound line product.'))
            duplicate_line = self.sudo().search([
                ('bonded_inbound_id', '=', rec.bonded_inbound_id.id),
                ('customs_file_line_id', '=', rec.customs_file_line_id.id),
                ('id', '!=', rec.id),
            ], limit=1)
            if duplicate_line:
                raise ValidationError(_('A declaration line can only be selected once in an inbound instruction.'))

    @api.constrains('product_id')
    def check_traceability_line_product(self):
        env_traceability_line = self.env['bonded.inbound.traceability.line'].sudo()
        for rec in self:
            traceability_lines = env_traceability_line.search([('inbound_line_id', '=', rec.id)])
            if traceability_lines.filtered(lambda line: line.product_id != rec.product_id):
                raise ValidationError(_('The traceability line product must match the inbound product line.'))

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
