# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError,ValidationError
from odoo.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)


class BondedOutbound(models.Model):
    _name = 'bonded.outbound'
    _description = 'Bonded Outbound Instruction - 保税出库指令'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(string='Outbound No.', required=True, copy=False,
                       default=lambda self: _('New'), readonly=True, index=True)
    order_type = fields.Selection([('outbound', 'Outbound')], string='Order Type', required=True, default='outbound', tracking=True)
    order_date = fields.Date(string='Order Date', required=True, default=fields.Date.today, tracking=True)
    bonded_book_id = fields.Many2one('bonded.book', string='Bonded Book', required=True, ondelete='restrict', index=True, domain=[('state', '=', 'active')], tracking=True)
    project_id = fields.Many2one('project.project', string='Project', required=True, ondelete='restrict', index=True, tracking=True)
    owner_id = fields.Many2one('res.partner', related='project_id.owner', string='Owner', store=True, readonly=True, index=True)
    reference = fields.Char(string='Reference', copy=False, index=True, tracking=True)
    is_dangerous = fields.Boolean(string='Dangerous Goods', default=False, tracking=True)
    customs_file_ids = fields.One2many('bonded.customs.file', 'bonded_outbound_id', string='Customs Declarations', tracking=True)
    t1_status = fields.Selection([('draft', 'Draft'), ('to_be_submitted', 'To Be Submitted'), ('submitted', 'Submitted'), ('customs_approved', 'Customs Approved'), ('customs_rejected', 'Customs Rejected'), ('done', 'Closed'), ('cancelled', 'Cancelled')], string='T1 Status', compute='_compute_t1_status', store=True, readonly=True, index=True)
    t1_closed_date = fields.Datetime(string='T1 Closed Date', compute='_compute_t1_status', store=True, readonly=True, index=True)
    outbound_type = fields.Selection([
        ('l2f', 'Clearance Outbound'),
        ('t1_transit', 'Bonded Outbound'),
        ('destruction', 'Destruction'),
    ], string='Outbound Type', required=True, tracking=True)
    mrn_id = fields.Many2one('bonded.mrn', string='Corresponding MRN', ondelete='restrict', index=True, copy=False, tracking=True)
    mrn = fields.Char(string='Corresponding MRN', index=True, help='Outbound MRN (T1 transit only)', tracking=True)
    mrn_status = fields.Selection(related='mrn_id.state', string='MRN Status', store=True, readonly=True, index=True)
    expected_date = fields.Date(string='Planned Date', required=True, tracking=True)
    total_value = fields.Monetary(string='Total Value', compute='_compute_total_value', store=True, readonly=True, tracking=True)
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.ref('base.EUR').id, tracking=True)
    picking_id = fields.Many2one('stock.picking', string='Stock Picking',
                                 readonly=True, ondelete='restrict', tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('declared', 'Declared'),
        ('released', 'Released'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True, index=True)
    line_ids = fields.One2many('bonded.outbound.line', 'bonded_outbound_id', string='Products', tracking=True)
    remark = fields.Text(string='Remark', tracking=True)
    remark1 = fields.Text(string='Remark 1', tracking=True)
    confirm_user_id = fields.Many2one('res.users', string='Confirmed By', readonly=True, copy=False, index=True, tracking=True)
    confirm_time_user_tz = fields.Datetime(string='Confirm Time (User Timezone)', readonly=True, copy=False, tracking=True)
    confirm_time_server = fields.Datetime(string='Confirm Time (Server)', readonly=True, copy=False, tracking=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    warehouse = fields.Many2one('stock.warehouse', string='Warehouse', tracking=True,
                                stored=True)
    warehouse_address = fields.Char(related='warehouse.partner_id.contact_address', string='Warehouse Address', readonly=True)
    pick_type = fields.Many2one('stock.picking.type', string='Picking Type', tracking=True,
                                domain=[('code', 'in', ['outgoing', 'internal'])])
    outbound_scan_mode = fields.Selection([('whole_pallet', 'Whole Pallet'), ('partial_pallet', 'Break Bulk')], string='Outbound Scan Mode', default='partial_pallet', required=True, copy=False, tracking=True)
    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Outbound number must be unique!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'mrn_id' in vals:
                vals['mrn'] = self.env['bonded.mrn'].sudo().browse(vals['mrn_id']).mrn if vals['mrn_id'] else False
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('seq.bonded.outbound') or _('New')
        return super().create(vals_list)

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        result = super().fields_get(allfields=allfields, attributes=attributes)
        if result.get('outbound_type', {}).get('selection'):
            result['outbound_type']['selection'] = [selection for selection in result['outbound_type']['selection'] if selection[0] != 'destruction']
        return result

    def write(self, vals):
        if 'mrn_id' in vals:
            vals['mrn'] = self.env['bonded.mrn'].sudo().browse(vals['mrn_id']).mrn if vals['mrn_id'] else False
        return super().write(vals)

    @api.onchange('project_id')
    def onchange_project_id(self):
        for rec in self:
            if rec.project_id:
                rec.warehouse = rec.project_id.warehouse
                rec.pick_type = rec.project_id.outbound_pick_type

    @api.depends('customs_file_ids.declaration_type', 'customs_file_ids.state', 'customs_file_ids.t1_closed_date')
    def _compute_t1_status(self):
        for rec in self:
            t1_files = rec.customs_file_ids.filtered(lambda item: item.declaration_type == 't1_out')
            t1_file = t1_files.sorted(key=lambda item: item.id, reverse=True)[:1]
            rec.t1_status = t1_file.state if t1_file else False
            rec.t1_closed_date = t1_file.t1_closed_date if t1_file else False
            rec.mrn_id = False
            rec.mrn = False

    @api.onchange('mrn_id')
    def onchange_mrn_id(self):
        for rec in self:
            rec.mrn = rec.mrn_id.mrn

    @api.constrains('outbound_type', 'customs_file_ids')
    def check_outbound_customs_file(self):
        for rec in self:
            required_type = 't1_out' if rec.outbound_type == 't1_transit' else 'clearance_out'
            if rec.customs_file_ids.filtered(lambda customs_file: customs_file.declaration_type != required_type):
                raise ValidationError(_('The selected customs declaration does not match the outbound type.'))
            if rec.customs_file_ids.filtered(lambda customs_file: customs_file.bonded_book_id != rec.bonded_book_id):
                raise ValidationError(_('The customs declarations and outbound instruction must use the same bonded book.'))

    @api.depends('line_ids.subtotal_value')
    def _compute_total_value(self):
        for rec in self:
            rec.total_value = sum(rec.line_ids.mapped('subtotal_value'))

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft outbound instructions can be confirmed.'))
            if not rec.line_ids:
                raise UserError(_('Please add outbound lines before confirming.'))
            for line in rec.line_ids:
                if not line.bonded_stock_id:
                    raise UserError(_('Please select bonded stock for each outbound line.'))
                if line.bonded_stock_id.current_customs_status != 'entrepot':
                    raise UserError(_('Only bonded stock in entrepot status can be outbound.'))
                if line.bonded_stock_id.quantity < line.demand_qty:
                    raise UserError(_('Insufficient bonded stock for tracking no. %s.') % line.inbound_tracking_no)
            rec.lock_stock()
            now = fields.Datetime.now()
            rec.write({
                'state': 'confirmed',
                'confirm_user_id': self.env.user.id,
                'confirm_time_user_tz': fields.Datetime.to_string(fields.Datetime.context_timestamp(rec, now)),
                'confirm_time_server': now,
            })

    def action_create_outbound_customs_file(self):
        customs_file = self.env['bonded.customs.file']
        for rec in self:
            declaration_type = 't1_out' if rec.outbound_type == 't1_transit' else 'clearance_out'
            if rec.state not in ('confirmed', 'declared'):
                raise UserError(_('Only confirmed or declared outbound instructions can create the matching outbound customs declaration.'))
            active_customs_files = rec.customs_file_ids.filtered(lambda item: item.state != 'cancelled')
            if active_customs_files:
                raise UserError(_('This outbound instruction already has an active customs declaration. Return a rejected file to draft and edit it, or cancel the existing file before creating another.'))
            eori_entity = rec.bonded_book_id.eori_entity_id
            line_vals = []
            for item_no, line in enumerate(rec.line_ids, 1):
                gross_weight = line.demand_qty * line.bonded_product_id.gross_weight
                net_weight = line.demand_qty * line.bonded_product_id.net_weight
                line_vals.append((0, 0, {
                    'item_no': item_no,
                    'bonded_product_id': line.bonded_product_id.id,
                    'product_id': line.product_id.id,
                    'origin_country_id': eori_entity.country_id.id,
                    'quantity': line.demand_qty,
                    'gross_weight': gross_weight,
                    'net_weight': net_weight,
                    'line_value': line.subtotal_value,
                    'currency_id': rec.currency_id.id,
                }))
            customs_file = self.env['bonded.customs.file'].create({
                'bonded_book_id': rec.bonded_book_id.id,
                'bonded_outbound_id': rec.id,
                'declaration_type': declaration_type,
                'customs_code': rec.bonded_book_id.customs_office_code,
                'consignor_eori_entity_id': eori_entity.id,
                'consignee_eori_entity_id': eori_entity.id,
                'declarant_eori_entity_id': eori_entity.id,
                'origin_country_id': eori_entity.country_id.id,
                'destination_country_id': eori_entity.country_id.id,
                'total_packages': sum(rec.line_ids.mapped('demand_qty')),
                'total_gross_weight': sum(line.demand_qty * line.bonded_product_id.gross_weight for line in rec.line_ids),
                'invoice_amount': rec.total_value,
                'currency_id': rec.currency_id.id,
                'line_ids': line_vals,
            })
        return {'type': 'ir.actions.act_window', 'res_model': 'bonded.customs.file', 'res_id': customs_file.id, 'view_mode': 'form', 'target': 'current'}

    def action_start(self):
        for rec in self:
            if rec.state != 'released':
                raise UserError(_('Only released outbound instructions can be started.'))
            rec.write({'state': 'in_progress'})

    def action_done(self):
        for rec in self:
            if rec.state != 'in_progress':
                raise UserError(_('Only in-progress instructions can be set to done.'))
            if not rec.picking_id:
                raise UserError(_('Please create and validate a stock picking first.'))
            customs_file = rec.customs_file_ids[:1]
            for move_line in rec.picking_id.move_line_ids:
                outbound_line = move_line.bonded_outbound_line_id or move_line.move_id.bonded_outbound_line_id
                source_stock = move_line.bonded_stock_id or move_line.move_id.bonded_stock_id or outbound_line.bonded_stock_id
                if not outbound_line or not source_stock:
                    continue
                done_qty = move_line.quantity
                if done_qty <= 0:
                    continue
                if source_stock.quantity < done_qty:
                    raise UserError(_('Outbound quantity exceeds bonded stock quantity for %s.') % source_stock.inbound_tracking_no)
                to_status = {
                    't1_transit': 'in_t1_transit',
                    'destruction': 'destroyed',
                }.get(rec.outbound_type, 'vrij')
                if done_qty < source_stock.quantity:
                    source_stock.write({'quantity': source_stock.quantity - done_qty, 'locked': False})
                    moved_stock = self.env['bonded.stock'].create({
                        'bonded_book_id': source_stock.bonded_book_id.id,
                        'product_id': source_stock.product_id.id,
                        'stock_move_line_id': move_line.id,
                        'lot_id': source_stock.lot_id.id if source_stock.lot_id else False,
                        'location_id': move_line.location_dest_id.id,
                        'inbound_id': source_stock.inbound_id.id,
                        'inbound_line_id': source_stock.inbound_line_id.id,
                        'inbound_tracking_no': source_stock.inbound_tracking_no,
                        'current_customs_status': to_status,
                        'quantity': done_qty,
                        'unit_value': source_stock.unit_value,
                        'currency_id': source_stock.currency_id.id,
                        'inbound_date': source_stock.inbound_date,
                        'outbound_customs_file_id': customs_file.id,
                        'related_t1_out_mrn': rec.mrn if rec.outbound_type == 't1_transit' else False,
                    })
                else:
                    source_stock.write({
                        'current_customs_status': to_status,
                        'locked': False,
                        'location_id': move_line.location_dest_id.id,
                        'outbound_customs_file_id': customs_file.id,
                        'related_t1_out_mrn': rec.mrn if rec.outbound_type == 't1_transit' else False,
                    })
                    moved_stock = source_stock
                self.env['bonded.verification'].create({
                    'bonded_book_id': rec.bonded_book_id.id,
                    'verification_type': 'outbound',
                    'customs_file_id': customs_file.id,
                    'bonded_stock_id': moved_stock.id,
                    'from_status': 'entrepot',
                    'to_status': to_status,
                    'quantity': done_qty,
                    'write_off_value': source_stock.unit_value * done_qty,
                    'operator_id': self.env.user.id,
                    'mrn': rec.mrn or False,
                })
                self.env['bonded.book.line'].create({
                    'bonded_book_id': rec.bonded_book_id.id,
                    'date': fields.Date.today(),
                    'operation_type': {'t1_transit': 't1_outbound', 'destruction': 'destruction'}.get(rec.outbound_type, 'customs_outbound'),
                    'product_id': source_stock.product_id.id,
                    'qty_change': -done_qty,
                    'from_status': 'entrepot',
                    'to_status': to_status,
                    'direction': 'out',
                    'ref_doc_no': rec.name,
                    'inbound_tracking_no': source_stock.inbound_tracking_no,
                    'bonded_stock_id': source_stock.id,
                    'customs_file_id': customs_file.id,
                    'picking_id': rec.picking_id.id,
                })
            rec.write({'state': 'done'})

    def action_cancel(self):
        for rec in self:
            if rec.state not in ('draft', 'confirmed', 'declared') or rec.picking_id:
                raise UserError(_('Only draft, confirmed, or declared outbound instructions without a picking can be cancelled.'))
            active_customs_files = rec.customs_file_ids.filtered(lambda item: item.state != 'cancelled')
            if active_customs_files:
                raise UserError(_('Cancel the active customs declaration before cancelling this outbound instruction.'))
            rec.line_ids.mapped('bonded_stock_id').write({'locked': False})
            self.env['bonded.log'].create({
                'model_name': 'bonded.outbound',
                'res_id': rec.id,
                'operation_type': 'action_cancel',
                'operation_detail': _('Cancelled with stock unlock.'),
            })
            rec.write({'state': 'cancelled'})

    def lock_stock(self):
        for rec in self:
            for line in rec.line_ids:
                stock = line.bonded_stock_id
                if not stock:
                    raise UserError(_('Please select bonded stock for each outbound line.'))
                if stock.locked:
                    raise UserError(_('Bonded stock %s is already locked.') % stock.display_name)
                if stock.current_customs_status != 'entrepot' or stock.quantity < line.demand_qty:
                    raise UserError(_('Insufficient available bonded stock for %s.') % stock.inbound_tracking_no)
                stock.write({'locked': True})

    def action_create_picking(self):
        self.ensure_one()
        if self.state != 'released':
            raise UserError(_('Only released instructions can create pickings.'))
        if self.picking_id:
            raise UserError(_('Stock picking already exists.'))
        scan_enabled = self.project_id.barcode_scan_mode == 'custom' and self.pick_type.code == 'outgoing'
        if scan_enabled:
            quant_model = self.env['stock.quant'].sudo()
            for line in self.line_ids:
                package = line.bonded_stock_id.package_id
                if not package:
                    raise UserError(_('Bonded stock %s has no pallet for outbound scanning.') % line.bonded_stock_id.display_name)
                quants = quant_model.search([('package_id', '=', package.id), ('product_id', '=', line.product_id.id), ('location_id', '=', line.bonded_stock_id.location_id.id), ('lot_id', '=', line.bonded_stock_id.lot_id.id or False)])
                available_quantity = sum(quants.mapped('available_quantity'))
                if float_compare(available_quantity, line.demand_qty, precision_rounding=line.uom_id.rounding) < 0:
                    raise UserError(_('Pallet %s does not contain enough available stock for %s.') % (package.display_name, line.product_id.display_name))
        if any(not line.bonded_stock_id.locked for line in self.line_ids):
            self.lock_stock()
        customs_file = self.customs_file_ids[:1]
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.pick_type.id,
            'location_id': self.pick_type.default_location_src_id.id,
            'location_dest_id': self.pick_type.default_location_dest_id.id,
            'origin': self.name,
            'bonded_outbound_id': self.id,
            'unique_identifier_no': ', '.join(sorted(set(filter(None, self.line_ids.mapped('inbound_tracking_no'))))),
            'bonded_customs_file_id': customs_file.id,
        })
        env_stock_move = self.env['stock.move']
        env_stock_move_line = self.env['stock.move.line']
        move_vals_by_key = {}
        for line in self.line_ids:
            uom_id = line.uom_id.id or line.product_id.uom_id.id
            move_key = (line.product_id.id, uom_id, line.bonded_stock_id.location_id.id, picking.location_dest_id.id)
            if move_key not in move_vals_by_key:
                move_vals_by_key[move_key] = {'name': line.product_id.name, 'product_id': line.product_id.id, 'product_uom_qty': line.demand_qty, 'product_uom': uom_id, 'picking_id': picking.id, 'location_id': line.bonded_stock_id.location_id.id, 'location_dest_id': picking.location_dest_id.id}
            else:
                move_vals_by_key[move_key]['product_uom_qty'] += line.demand_qty
        moves = env_stock_move.create(list(move_vals_by_key.values()))
        moves_by_key = dict(zip(move_vals_by_key, moves))
        move_line_vals = []
        for line in self.line_ids:
            uom_id = line.uom_id.id or line.product_id.uom_id.id
            move_key = (line.product_id.id, uom_id, line.bonded_stock_id.location_id.id, picking.location_dest_id.id)
            move_line_vals.append({'picking_id': picking.id, 'move_id': moves_by_key[move_key].id, 'product_id': line.product_id.id, 'product_uom_id': uom_id, 'quantity': line.demand_qty, 'location_id': line.bonded_stock_id.location_id.id, 'location_dest_id': picking.location_dest_id.id, 'package_id': line.bonded_stock_id.package_id.id, 'lot_id': line.bonded_stock_id.lot_id.id, 'bonded_stock_id': line.bonded_stock_id.id, 'bonded_outbound_line_id': line.id})
        env_stock_move_line.create(move_line_vals)
        if scan_enabled:
            picking.write({'outbound_scan_mode': self.outbound_scan_mode})
        self.write({'picking_id': picking.id, 'state': 'in_progress'})
        return {'type': 'ir.actions.client', 'tag': 'reload'}


class BondedOutboundLine(models.Model):
    _name = 'bonded.outbound.line'
    _description = 'Bonded Outbound Line'
    _order = 'bonded_outbound_id, id'

    bonded_outbound_id = fields.Many2one('bonded.outbound', string='Outbound Instruction', required=True, ondelete='cascade', index=True)
    bonded_stock_id = fields.Many2one('bonded.stock', string='Bonded Stock', required=True, ondelete='restrict', index=True, domain=[('current_customs_status', '=', 'entrepot'), ('quantity', '>', 0), ('locked', '=', False)])
    bonded_product_id = fields.Many2one('bonded.product', string='Bonded Product Filing', ondelete='restrict', index=True)
    product_id = fields.Many2one('product.product', string='Product', index=True)
    inbound_tracking_no = fields.Char(string='Unique Identifier No.', related='bonded_stock_id.inbound_tracking_no', store=True, index=True)
    demand_qty = fields.Float(string='Demand Qty', required=True, default=1.0)
    declared_unit_price = fields.Monetary(string='Declared Unit Price', required=True, default=0.0)
    subtotal_value = fields.Monetary(string='Subtotal', compute='_compute_subtotal_value', store=True)
    currency_id = fields.Many2one('res.currency', related='bonded_outbound_id.currency_id', string='Currency', readonly=True)
    done_qty = fields.Float(string='Done Qty', compute='_compute_done_qty', store=True)
    uom_id = fields.Many2one('uom.uom', string='UoM', required=True)
    eligible_bonded_product_ids = fields.Many2many('bonded.product', compute='_compute_eligible_bonded_product_ids')

    @api.model_create_multi
    def create(self, vals_list):
        env_bonded_outbound = self.env['bonded.outbound'].sudo()
        env_bonded_product = self.env['bonded.product'].sudo()
        env_bonded_stock = self.env['bonded.stock'].sudo()
        for vals in vals_list:
            outbound = env_bonded_outbound.browse(vals.get('bonded_outbound_id')).exists()
            if not outbound:
                continue
            filing = env_bonded_product.browse(vals.get('bonded_product_id')).exists()
            if filing:
                vals['product_id'] = filing.product_id.id
                vals.setdefault('uom_id', filing.product_id.uom_id.id)
            elif vals.get('product_id'):
                filing = env_bonded_product.search([
                    ('bonded_book_id', '=', outbound.bonded_book_id.id),
                    ('product_id', '=', vals['product_id']),
                    ('state', '=', 'active'),
                ], limit=1)
            if filing:
                vals.setdefault('bonded_product_id', filing.id)
            bonded_stock = env_bonded_stock.browse(vals.get('bonded_stock_id')).exists()
            if bonded_stock:
                vals.setdefault('declared_unit_price', bonded_stock.unit_value)
                vals.setdefault('uom_id', bonded_stock.product_id.uom_id.id)
        return super().create(vals_list)

    @api.constrains('bonded_outbound_id', 'bonded_stock_id', 'bonded_product_id', 'product_id')
    def check_bonded_stock_product(self):
        for rec in self:
            if rec.bonded_product_id and (rec.bonded_product_id.bonded_book_id != rec.bonded_outbound_id.bonded_book_id or rec.bonded_product_id.product_id != rec.product_id or rec.bonded_product_id.state != 'active'):
                raise ValidationError(_('The bonded product filing must be active and belong to the outbound instruction bonded book.'))
            if rec.bonded_stock_id and rec.product_id and rec.bonded_stock_id.product_id != rec.product_id:
                raise ValidationError(_('Selected inbound tracking stock does not match the product.'))

    @api.onchange('bonded_product_id')
    def onchange_bonded_product_id(self):
        for rec in self:
            if rec.bonded_product_id:
                rec.product_id = rec.bonded_product_id.product_id
                rec.uom_id = rec.bonded_product_id.product_id.uom_id

    @api.onchange('bonded_stock_id')
    def onchange_bonded_stock_id(self):
        for rec in self:
            if rec.bonded_stock_id:
                rec.product_id = rec.bonded_stock_id.product_id
                rec.uom_id = rec.bonded_stock_id.product_id.uom_id
                rec.declared_unit_price = rec.bonded_stock_id.unit_value

    def action_open_stock_selection(self):
        for rec in self:
            if rec.bonded_outbound_id.state != 'draft':
                raise UserError(_('Bonded stock can only be selected on a draft outbound instruction.'))
            if not rec.product_id:
                raise UserError(_('Please select a product before selecting bonded stock.'))
            return {
                'name': _('Select Bonded Stock'),
                'type': 'ir.actions.act_window',
                'res_model': 'bonded.stock',
                'view_mode': 'list',
                'views': [(self.env.ref('wd_bonded_wms.view_bonded_stock_m2o_tracking_list').id, 'list')],
                'target': 'new',
                'domain': [('bonded_book_id', '=', rec.bonded_outbound_id.bonded_book_id.id), ('product_id', '=', rec.product_id.id), ('quantity', '>', 0), ('locked', '=', False), ('current_customs_status', '=', 'entrepot'), ('inbound_id.state', '=', 'done'), ('inbound_id.picking_id.state', '=', 'done')],
                'context': {'bonded_outbound_line_id': rec.id},
            }
        return False

    @api.depends('demand_qty', 'declared_unit_price')
    def _compute_subtotal_value(self):
        for rec in self:
            rec.subtotal_value = rec.demand_qty * rec.declared_unit_price

    @api.depends('bonded_outbound_id.bonded_book_id')
    def _compute_eligible_bonded_product_ids(self):
        for rec in self:
            book = rec.bonded_outbound_id.bonded_book_id
            rec.eligible_bonded_product_ids = self.env['bonded.product'].sudo().search([
                ('bonded_book_id', '=', book.id),
                ('state', '=', 'active'),
            ]) if book else self.env['bonded.product']

    @api.depends('bonded_outbound_id.picking_id.move_line_ids.quantity', 'bonded_outbound_id.picking_id.move_line_ids.move_id.state', 'bonded_outbound_id.picking_id.move_line_ids.bonded_outbound_line_id', 'bonded_outbound_id.picking_id.move_ids.bonded_outbound_line_id')
    def _compute_done_qty(self):
        for rec in self:
            if rec.bonded_outbound_id.picking_id:
                move_lines = rec.bonded_outbound_id.picking_id.move_line_ids.filtered(
                    lambda line: (line.bonded_outbound_line_id == rec or line.move_id.bonded_outbound_line_id == rec) and line.move_id.state == 'done'
                )
                rec.done_qty = sum(move_lines.mapped('quantity'))
            else:
                rec.done_qty = 0.0
