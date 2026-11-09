# -*- coding: utf-8 -*-
import logging
import re
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class BondedCustomsFile(models.Model):
    _name = 'bonded.customs.file'
    _description = 'Customs Declaration File'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'declaration_no'
    _order = 'declaration_date desc, id desc'

    bonded_book_id = fields.Many2one('bonded.book', string='Bonded Book', required=True, ondelete='restrict', index=True, domain=[('state', '=', 'active')], tracking=True)
    bonded_inbound_id = fields.Many2one('bonded.inbound', string='Bonded Inbound', ondelete='restrict', index=True, copy=False, tracking=True)
    bonded_outbound_id = fields.Many2one('bonded.outbound', string='Bonded Outbound', ondelete='restrict', index=True, copy=False, tracking=True)
    declaration_type = fields.Selection([
        ('t1_in', 'T1 Transit Inbound'),
        ('clearance_out', 'Customs Clearance Outbound'),
        ('t1_out', 'T1 Transit Outbound'),
        ('destruction', 'Destruction'),
    ], string='Declaration Type', required=True, index=True, tracking=True)
    mrn_id = fields.Many2one('bonded.mrn', string='Corresponding MRN', ondelete='restrict', index=True, copy=False, tracking=True)
    mrn = fields.Char(string='Corresponding MRN', index=True, help='Movement Reference Number (T1 only)', tracking=True)
    declaration_no = fields.Char(string='Declaration No.(Box3)', required=True, copy=False, default=lambda self: _('New'), readonly=True, index=True)
    customs_code = fields.Char(string='Customs Code(Box5)', required=True, index=True, tracking=True, help='e.g. NLAMS001')
    consignor_eori_entity_id = fields.Many2one('bonded.eori.entity', string='Consignor EORI Entity', required=True, ondelete='restrict', index=True, tracking=True)
    consignee_eori_entity_id = fields.Many2one('bonded.eori.entity', string='Consignee EORI Entity', required=True, ondelete='restrict', index=True, tracking=True)
    declarant_eori_entity_id = fields.Many2one('bonded.eori.entity', string='Declarant EORI Entity', required=True, ondelete='restrict', index=True, tracking=True)
    consignor_eori = fields.Char(string='Consignor EORI(Box8)', index=True, tracking=True)
    consignee_eori = fields.Char(string='Consignee EORI(Box9)', index=True, tracking=True)
    declarant_eori = fields.Char(string='Declarant EORI', index=True, tracking=True)

    procedure_code = fields.Char(string='Procedure Code(Box37)', required=True, default='4000C51', index=True, tracking=True, help='e.g. 4000C51 for bonded warehouse')
    previous_doc_no = fields.Char(string='Previous Document No.(Box40)', index=True, tracking=True, help='T1 inbound: fill with handover DO number')
    bonded_warehouse_no = fields.Char(string='Bonded Warehouse No. (Box49)', index=True, tracking=True)
    origin_country_id = fields.Many2one('res.country', string='Country of Origin', required=True, tracking=True)
    destination_country_id = fields.Many2one('res.country', string='Country of Destination', required=True, tracking=True)
    transport_mode = fields.Selection([('sea', 'Sea'), ('road', 'Road'), ('air', 'Air'), ('rail', 'Rail')], string='Transport Mode', required=True, default='sea', tracking=True)
    estimated_distance_km = fields.Float(string='Estimated Distance (km)', tracking=True, help='Used for transit_deadline calculation. Road: +1 day per 500km')
    transit_deadline = fields.Datetime(string='Transit Deadline', tracking=True, help='Auto-calculated from transport_mode + distance, manually adjustable')
    total_packages = fields.Float(string='Total Packages', required=True, default=0.0, tracking=True)
    total_gross_weight = fields.Float(string='Total Gross Weight (kg)', required=True, default=0.0, tracking=True)
    invoice_amount = fields.Monetary(string='Invoice Amount', required=True, default=0.0, tracking=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.ref('base.EUR').id, tracking=True)
    declaration_date = fields.Datetime(string='Declaration Date', index=True, tracking=True)
    t1_closed_date = fields.Datetime(string='T1 Closed Date', readonly=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('to_be_submitted', 'To Be Submitted'),
        ('submitted', 'Submitted'),
        ('customs_approved', 'Customs Approved'),
        ('customs_rejected', 'Customs Rejected'),
        ('done', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True, index=True)

    # ===== 海关回执 =====
    rejection_reason = fields.Text(string='Rejection Reason', readonly=True, tracking=True)
    approval_no = fields.Char(string='Approval No.', readonly=True, tracking=True)
    approval_date = fields.Datetime(string='Approval Date', readonly=True, tracking=True)
    declaration_attachment_line_ids = fields.Many2many('ir.attachment', 'bonded_customs_file_declaration_attachment_rel', 'customs_file_id', 'attachment_id', string='Declaration Attachments', copy=False, tracking=True)
    response_attachment_line_ids = fields.Many2many('ir.attachment', 'bonded_customs_file_response_attachment_rel', 'customs_file_id', 'attachment_id', string='Customs Response Attachments', copy=False, tracking=True)
    line_ids = fields.One2many('bonded.customs.file.line', 'customs_file_id', string='Declaration Lines', tracking=True)
    gate_arrival_ids = fields.One2many('gate.arrival', 'customs_file_id', string='Gate Arrival', help='The current process allows one T1 gate arrival for this declaration.', tracking=True)
    inbound_tracking_ids = fields.One2many('bonded.inbound.tracking', 'customs_file_id', string='Unique Identifier No.', tracking=True)
    outbound_tracking_line_ids = fields.Many2many('bonded.inbound.tracking', string='Unique Identifier No.', compute='_compute_outbound_tracking_line_ids')
    mrn_ids = fields.One2many('bonded.mrn', 'customs_file_id', string='MRN Numbers', tracking=True)
    remark = fields.Text(string='Remark', tracking=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    @api.depends('bonded_outbound_id', 'bonded_outbound_id.line_ids.bonded_stock_id.inbound_line_id.bonded_inbound_id.inbound_tracking_id')
    def _compute_outbound_tracking_line_ids(self):
        for rec in self:
            rec.outbound_tracking_line_ids = rec.bonded_outbound_id.line_ids.mapped('bonded_stock_id.inbound_line_id.bonded_inbound_id.inbound_tracking_id')

    _sql_constraints = [
        ('declaration_no_uniq', 'unique(declaration_no)', 'Declaration number must be unique!'),
    ]

    @api.constrains('declaration_type', 'bonded_book_id', 'bonded_inbound_id', 'bonded_outbound_id')
    def check_instruction_link(self):
        for rec in self:
            if rec.bonded_inbound_id and rec.bonded_outbound_id:
                raise ValidationError(_('A customs declaration can only link to one inbound or outbound instruction.'))
            if rec.bonded_inbound_id and rec.declaration_type != 't1_in':
                raise ValidationError(_('Inbound instructions can only link to T1 inbound declarations.'))
            if rec.bonded_outbound_id:
                expected_type = 't1_out' if rec.bonded_outbound_id.outbound_type == 't1_transit' else 'clearance_out'
                if rec.declaration_type != expected_type:
                    raise ValidationError(_('The customs declaration type must match the outbound type.'))
            instruction = rec.bonded_inbound_id or rec.bonded_outbound_id
            if instruction and instruction.bonded_book_id != rec.bonded_book_id:
                raise ValidationError(_('The customs declaration and linked instruction must use the same bonded book.'))
            if rec.bonded_inbound_id and self.env['bonded.customs.file'].sudo().search([('bonded_inbound_id', '=', rec.bonded_inbound_id.id), ('id', '!=', rec.id), ('state', '!=', 'cancelled')], limit=1):
                raise ValidationError(_('An inbound instruction can only have one active customs declaration. Cancel the existing declaration before creating another.'))
            if rec.bonded_outbound_id and self.env['bonded.customs.file'].sudo().search([('bonded_outbound_id', '=', rec.bonded_outbound_id.id), ('id', '!=', rec.id), ('state', '!=', 'cancelled')], limit=1):
                raise ValidationError(_('An outbound instruction can only have one active customs declaration. Cancel the existing declaration before creating another.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'mrn_id' in vals:
                vals['mrn'] = self.env['bonded.mrn'].sudo().browse(vals['mrn_id']).mrn if vals['mrn_id'] else False
            if vals.get('mrn'):
                vals['mrn'] = vals['mrn'].strip().upper()
            for eori_field in ('consignor_eori', 'consignee_eori', 'declarant_eori'):
                if vals.get(eori_field):
                    vals[eori_field] = vals[eori_field].strip().upper()
            for entity_field, eori_field in (
                ('consignor_eori_entity_id', 'consignor_eori'),
                ('consignee_eori_entity_id', 'consignee_eori'),
                ('declarant_eori_entity_id', 'declarant_eori'),
            ):
                if vals.get(entity_field):
                    entity = self.env['bonded.eori.entity'].sudo().browse(vals[entity_field])
                    vals[eori_field] = entity.eori_no
            if vals.get('declaration_no', _('New')) == _('New'):
                seq_code = {
                    't1_in': 'seq.customs.file.t1_in',
                    'clearance_out': 'seq.customs.file.clearance_out',
                    't1_out': 'seq.customs.file.t1_out',
                    'destruction': 'seq.customs.file.destruction',
                }.get(vals.get('declaration_type'))
                if seq_code:
                    vals['declaration_no'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')
            if vals.get('transport_mode') and not vals.get('transit_deadline'):
                vals['transit_deadline'] = self.compute_transit_deadline(vals.get('transport_mode'), vals.get('estimated_distance_km', 0.0))
        customs_files = super().create(vals_list)
        for rec in customs_files:
            if rec.mrn and not rec.mrn_id:
                self.env['bonded.mrn'].create({'mrn': rec.mrn, 'customs_file_id': rec.id})
        return customs_files

    def write(self, vals):
        if 'mrn_id' in vals:
            vals['mrn'] = self.env['bonded.mrn'].sudo().browse(vals['mrn_id']).mrn if vals['mrn_id'] else False
        if vals.get('mrn'):
            vals['mrn'] = vals['mrn'].strip().upper()
        for eori_field in ('consignor_eori', 'consignee_eori', 'declarant_eori'):
            if vals.get(eori_field):
                vals[eori_field] = vals[eori_field].strip().upper()
        for entity_field, eori_field in (
            ('consignor_eori_entity_id', 'consignor_eori'),
            ('consignee_eori_entity_id', 'consignee_eori'),
            ('declarant_eori_entity_id', 'declarant_eori'),
        ):
            if vals.get(entity_field):
                entity = self.env['bonded.eori.entity'].sudo().browse(vals[entity_field])
                vals[eori_field] = entity.eori_no
        result = super().write(vals)
        if not self.env.context.get('skip_mrn_sync') and 'mrn' in vals:
            for rec in self:
                if rec.mrn_id and rec.mrn_id.mrn != rec.mrn:
                    rec.mrn_id.write({'mrn': rec.mrn})
                elif rec.mrn and not rec.mrn_id:
                    self.env['bonded.mrn'].create({'mrn': rec.mrn, 'customs_file_id': rec.id})
        if 'mrn_id' in vals:
            for rec in self:
                if rec.bonded_outbound_id and not rec.bonded_outbound_id.mrn_id:
                    rec.bonded_outbound_id.write({'mrn_id': rec.mrn_id.id})
        return result

    def unlink(self):
        for rec in self:
            if rec.declaration_no and rec.declaration_no != _('New'):
                raise UserError(_('Customs declaration with a generated number cannot be deleted. Please cancel it instead.'))
        return super().unlink()

    @api.constrains('mrn')
    def check_mrn(self):
        pattern = re.compile(r'^\d{2}[A-Z]{2}[A-Z0-9]{14}$')
        # for rec in self:
        #     if rec.mrn and not pattern.match(rec.mrn):
        #         raise ValidationError(_('MRN must be 18 characters: 2 digits + 2 letters + 14 letters/digits.'))

    @api.constrains('mrn_id')
    def check_mrn_customs_file(self):
        for rec in self:
            if rec.mrn_id and rec.mrn_id.customs_file_id != rec:
                raise ValidationError(_('The selected MRN must be bound to this customs declaration.'))

    def ensure_mrn_record(self):
        env_bonded_mrn = self.env['bonded.mrn'].sudo()
        for rec in self:
            if rec.mrn_id or not rec.mrn:
                continue
            mrn_record = env_bonded_mrn.search([('mrn', '=', rec.mrn)], limit=1)
            if mrn_record and mrn_record.customs_file_id != rec:
                raise ValidationError(_('MRN %s is already bound to another customs declaration.') % rec.mrn)
            if not mrn_record:
                mrn_record = self.env['bonded.mrn'].create({'mrn': rec.mrn, 'customs_file_id': rec.id})
            rec.write({'mrn_id': mrn_record.id})
        return self

    @api.onchange('mrn_id')
    def onchange_mrn_id(self):
        for rec in self:
            rec.mrn = rec.mrn_id.mrn

    def action_submit(self):
        for rec in self:
            if rec.state not in ('draft', 'to_be_submitted'):
                raise UserError(_('Only draft customs declarations can be submitted.'))
            if not rec.line_ids:
                raise UserError(_('Please add declaration lines before submitting.'))
            rec.validate_eori_parties()
            if rec.declaration_type in ('t1_in', 't1_out') and not rec.mrn:
                raise UserError(_('T1 declarations require an MRN before submission.'))
            # ---- 商品备案校验 ----
            if not rec.check_product_filing():
                raise UserError(_('Product filing check failed. Please verify bonded.product records.'))
            if rec.declaration_type == 't1_in' and rec.bonded_inbound_id:
                env_bonded_value_ledger = self.env['bonded.value.ledger'].sudo()
                value_ledger = env_bonded_value_ledger.search([('bonded_book_id', '=', rec.bonded_inbound_id.bonded_book_id.id), ('inbound_id', '=', rec.bonded_inbound_id.id)])
                if not sum(value_ledger.mapped('reserved_change')) and not sum(value_ledger.mapped('deducted_change')):
                    rec.bonded_inbound_id.bonded_book_id.reserve_document_value(rec.bonded_inbound_id.total_value, project_id=rec.bonded_inbound_id.project_id.id, inbound_id=rec.bonded_inbound_id.id)
            if not rec.check_value_limit():
                raise UserError(_('Value limit check failed. Please verify bonded.value.limit.'))
            rec.write({'state': 'submitted', 'declaration_date': fields.Datetime.now()})
            rec.sync_instruction_state('declared')

    def action_approve(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_('Only submitted declarations can be approved.'))
            if rec.declaration_type not in ('t1_in', 't1_out'):
                raise UserError(_('Only T1 declarations have a customs approval step.'))
            rec.write({
                'state': 'customs_approved',
                'approval_date': fields.Datetime.now(),
                'approval_no': self.env['ir.sequence'].next_by_code('seq.customs.approval') or 'APP-' + fields.Datetime.now().strftime('%Y%m%d%H%M%S'),
            })
            if rec.declaration_type == 't1_in':
                inbound = rec.bonded_inbound_id
                active_files = inbound.t1_customs_file_ids.filtered(lambda customs_file: customs_file.state not in ('customs_rejected', 'cancelled')) if inbound else self.env['bonded.customs.file']
                if inbound and active_files and all(customs_file.state in ('customs_approved', 'done') for customs_file in active_files):
                    bonded_book = self.env['bonded.book'].browse(inbound.bonded_book_id.id)
                    bonded_book.deduct_document_value(project_id=inbound.project_id.id, inbound_id=inbound.id, customs_file_id=rec.id)
            if rec.declaration_type == 't1_out':
                rec.sync_instruction_state('released')

    def action_reject(self, reason=''):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_('Only submitted declarations can be rejected.'))
            rec.write({'state': 'customs_rejected', 'rejection_reason': reason or _('Rejected by customs authority.')})
            inbound = rec.bonded_inbound_id
            if inbound:
                bonded_book = self.env['bonded.book'].browse(inbound.bonded_book_id.id)
                bonded_book.release_document_value(project_id=inbound.project_id.id, inbound_id=inbound.id, customs_file_id=rec.id)
            if rec.declaration_type == 't1_in':
                rec.reset_inbound_on_rejection()
            elif rec.declaration_type in ('clearance_out', 't1_out', 'destruction'):
                outbound = rec.bonded_outbound_id
                if outbound:
                    for stock in outbound.line_ids.mapped('bonded_stock_id'):
                        if not stock.locked:
                            stock.write({'locked': True})
                    if outbound.state in ('declared', 'released'):
                        outbound.write({'state': 'confirmed'})

    def action_done(self):
        """完成 T1 入库海关文件"""
        for rec in self:
            if rec.state != 'customs_approved':
                raise UserError(_('Only approved declarations can be set to done.'))
            if rec.declaration_type != 't1_in':
                raise UserError(_('Use Close T1 to complete a T1 outbound declaration.'))
            rec.write({'state': 'done'})
            if rec.declaration_type == 't1_in':
                closed_date = fields.Datetime.now()
                rec.write({'t1_closed_date': closed_date})
                rec.ensure_mrn_record()
                rec.sync_instruction_state('released')

    def release_outbound_value(self):
        for rec in self:
            outbound_records = rec.bonded_outbound_id
            for outbound in outbound_records:
                bonded_book = self.env['bonded.book'].browse(outbound.bonded_book_id.id)
                ledger_records = self.env['bonded.value.ledger'].sudo().search([('bonded_book_id', '=', bonded_book.id), ('project_id', '=', outbound.project_id.id)])
                if sum(ledger_records.mapped('deducted_change')) < outbound.total_value:
                    raise UserError(_('The deducted value is insufficient for outbound release.'))
                bonded_book.create_value_ledger('release', outbound.total_value, project_id=outbound.project_id.id, outbound_id=outbound.id, customs_file_id=rec.id, release_from_deduction=True)

    def action_complete_clearance(self):
        for rec in self:
            if rec.declaration_type != 'clearance_out' or rec.state != 'submitted':
                raise UserError(_('Only submitted customs clearance outbound declarations can be completed.'))
            rec.write({'state': 'done'})
            outbound = rec.bonded_outbound_id
            active_files = outbound.customs_file_ids.filtered(lambda customs_file: customs_file.state not in ('customs_rejected', 'cancelled')) if outbound else self.env['bonded.customs.file']
            if outbound and active_files and all(customs_file.state == 'done' for customs_file in active_files):
                rec.release_outbound_value()
            rec.sync_instruction_state('released')

    def action_close_t1(self):
        for rec in self:
            if rec.declaration_type != 't1_out' or rec.state != 'customs_approved':
                raise UserError(_('Only approved T1 outbound declarations can be closed.'))
            outbound = rec.bonded_outbound_id
            if not outbound or outbound.state != 'done' or not outbound.picking_id or outbound.picking_id.state != 'done':
                raise UserError(_('Complete all related outbound pickings before closing the T1 declaration.'))
            rec.write({'state': 'done', 't1_closed_date': fields.Datetime.now()})
            active_files = outbound.customs_file_ids.filtered(lambda customs_file: customs_file.state not in ('customs_rejected', 'cancelled'))
            if active_files and all(customs_file.state == 'done' for customs_file in active_files):
                rec.release_outbound_value()

    def action_cancel(self):
        for rec in self:
            if rec.state not in ('draft', 'to_be_submitted', 'submitted'):
                raise UserError(_('Only draft/to_submit/submitted declarations can be cancelled.'))
            rec.write({'state': 'cancelled'})
            if rec.bonded_outbound_id and rec.mrn_id and rec.bonded_outbound_id.mrn_id == rec.mrn_id:
                rec.bonded_outbound_id.write({'mrn_id': False})
            if rec.bonded_inbound_id or rec.bonded_outbound_id:
                rec.sync_instruction_state('released')

    def action_return_to_draft(self):
        for rec in self:
            if rec.state != 'customs_rejected':
                raise UserError(_('Only customs-rejected declarations can be returned to draft.'))
            rec.write({'state': 'draft'})

    def validate_eori_parties(self):
        pattern = re.compile(r'^[A-Z]{2}[A-Z0-9]{2,15}$')
        check_date = fields.Date.today()
        for rec in self:
            for entity, eori_no, label in (
                (rec.consignor_eori_entity_id, rec.consignor_eori, _('Consignor EORI')),
                (rec.consignee_eori_entity_id, rec.consignee_eori, _('Consignee EORI')),
                (rec.declarant_eori_entity_id, rec.declarant_eori, _('Declarant EORI')),
            ):
                if not entity:
                    raise UserError(_('%s entity is required.') % label)
                entity.validate_active_on_date(check_date)
                if entity.eori_no != eori_no:
                    raise UserError(_('%s does not match the selected EORI entity.') % label)
                if not eori_no or not pattern.match(eori_no.strip().upper()):
                    raise UserError(_('%s is required and must follow the formal EORI format: 2 uppercase letters for the country code followed by 2 to 15 uppercase letters or digits, with a total length of 4 to 17 characters, for example NL123456789.') % label)
        return True

    def check_value_limit(self):
        self.ensure_one()
        return self.bonded_book_id.available_value >= 0

    def check_product_filing(self):
        self.ensure_one()
        for line in self.line_ids:
            filing = self.env['bonded.product'].sudo().search([
                ('bonded_book_id', '=', self.bonded_book_id.id),
                ('product_id', '=', line.product_id.id),
                ('state', '=', 'active'),
            ], limit=1)
            if not filing:
                return False
        return True

    def compute_transit_deadline(self, transport_mode, distance_km=0.0):
        """根据运输方式和距离自动计算transit_deadline"""
        base_days = {'road': 2, 'sea': 7, 'air': 3, 'rail': 5}.get(transport_mode, 7)
        extra_days = int((distance_km - 500) / 500) + 1 if transport_mode == 'road' and distance_km > 500 else 0
        return fields.Datetime.now() + timedelta(days=base_days + extra_days)

    def sync_instruction_state(self, target_state):
        for rec in self:
            if rec.declaration_type == 't1_in':
                inbound = rec.bonded_inbound_id
                if not inbound:
                    raise UserError(_('Please link a bonded inbound instruction before submitting this T1 declaration.'))
                if inbound.state not in ('confirmed', 'declared', 'released'):
                    raise UserError(
                        _('Please confirm linked inbound instructions before submitting customs declaration.'))
                if target_state == 'declared':
                    if inbound.state == 'confirmed':
                        inbound.write({'state': 'declared'})
                elif target_state == 'released':
                    active_files = inbound.t1_customs_file_ids.filtered(lambda customs_file: customs_file.state not in ('customs_rejected', 'cancelled'))
                    if active_files and all(customs_file.state == 'done' for customs_file in active_files) and inbound.state in ('confirmed', 'declared'):
                        inbound.write({'state': 'released'})

            elif rec.declaration_type in ('clearance_out', 't1_out', 'destruction'):
                outbound = rec.bonded_outbound_id
                if not outbound:
                    raise UserError(
                        _('Please create and link a bonded outbound instruction before submitting this declaration.'))

                if outbound.state not in ('confirmed', 'declared', 'released'):
                    raise UserError(
                        _('Please confirm linked outbound instructions before submitting customs declaration.'))
                if target_state == 'declared' and outbound.state == 'confirmed':
                    outbound.write({'state': 'declared'})
                elif target_state == 'released':
                    active_files = outbound.customs_file_ids.filtered(lambda customs_file: customs_file.state not in ('customs_rejected', 'cancelled'))
                    ready_states = ('customs_approved', 'done') if rec.declaration_type == 't1_out' else ('done',)
                    if active_files and all(customs_file.state in ready_states for customs_file in active_files) and outbound.state in ('confirmed', 'declared'):
                        outbound.write({'state': 'released'})
#入库报关被拒绝
    def reset_inbound_on_rejection(self):
        for rec in self:
            inbound = rec.bonded_inbound_id
            if inbound and inbound.state in ('declared', 'released'):
                inbound.write({'state': 'confirmed'})

    @api.model
    def cron_monitor_t1_deadlines(self):
        customs_files = self.env['bonded.customs.file'].sudo().search([
            ('declaration_type', 'in', ('t1_in', 't1_out')),
            ('state', 'in', ('submitted', 'customs_approved')),
            ('transit_deadline', '<', fields.Datetime.now()),
        ])
        for customs_file in customs_files:
            _logger.warning('T1 transit deadline exceeded: %s, MRN: %s', customs_file.declaration_no, customs_file.mrn)
        return True
