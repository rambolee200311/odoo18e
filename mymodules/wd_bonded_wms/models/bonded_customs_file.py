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

    bonded_book_id = fields.Many2one('bonded.book', string='Bonded Book', required=True, ondelete='restrict', index=True)
    declaration_type = fields.Selection([
        ('t1_in', 'T1 Transit Inbound'),
        ('b3_in', 'B3 Bonded Inbound'),
        ('b3_out', 'B3 Customs Clearance(L2F)'),
        ('t1_out', 'T1 Transit Outbound'),
        ('ex', 'EU Dispatch'),
        ('destruction', 'Destruction'),
    ], string='Declaration Type', required=True, index=True, tracking=True)
    mrn_id = fields.Many2one('bonded.mrn', string='MRN Number', ondelete='restrict', index=True, copy=False)
    mrn = fields.Char(string='MRN Number', index=True, help='Movement Reference Number (T1 only)')
    declaration_no = fields.Char(string='Declaration No.(Box3)', required=True, copy=False, default=lambda self: _('New'), readonly=True, index=True)
    customs_code = fields.Char(string='Customs Code(Box5)', required=True, index=True,help='e.g. NLAMS001')
    consignor_eori_entity_id = fields.Many2one('bonded.eori.entity', string='Consignor EORI Entity', required=True, ondelete='restrict', index=True)
    consignee_eori_entity_id = fields.Many2one('bonded.eori.entity', string='Consignee EORI Entity', required=True, ondelete='restrict', index=True)
    declarant_eori_entity_id = fields.Many2one('bonded.eori.entity', string='Declarant EORI Entity', required=True, ondelete='restrict', index=True)
    consignor_eori = fields.Char(string='Consignor EORI(Box8)', index=True)
    consignee_eori = fields.Char(string='Consignee EORI(Box9)', index=True)
    declarant_eori = fields.Char(string='Declarant EORI', index=True)

    procedure_code = fields.Char(string='Procedure Code(Box37)', required=True, default='4000C51', index=True, help='e.g. 4000C51 for bonded warehouse')
    previous_doc_no = fields.Char(string='Previous Document No.(Box40)', index=True,help='T1 inbound: fill with handover DO number')
    bonded_warehouse_no = fields.Char(string='Bonded Warehouse No. (Box49)', index=True)
    origin_country_id = fields.Many2one('res.country', string='Country of Origin', required=True)
    destination_country_id = fields.Many2one('res.country', string='Country of Destination', required=True)
    transport_mode = fields.Selection([('sea', 'Sea'), ('road', 'Road'), ('air', 'Air'), ('rail', 'Rail')], string='Transport Mode', required=True, default='sea')
    estimated_distance_km = fields.Float(string='Estimated Distance (km)',help='Used for transit_deadline calculation. Road: +1 day per 500km')
    transit_deadline = fields.Datetime(string='Transit Deadline',help='Auto-calculated from transport_mode + distance, manually adjustable')
    total_packages = fields.Float(string='Total Packages', required=True, default=0.0)
    total_gross_weight = fields.Float(string='Total Gross Weight (kg)', required=True, default=0.0)
    invoice_amount = fields.Monetary(string='Invoice Amount', required=True, default=0.0)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.ref('base.EUR').id)
    declaration_date = fields.Datetime(string='Declaration Date', index=True)
    pre_condition = fields.Selection([('none', 'No Pre-condition'), ('t1_closed', 'T1 Must Be Closed')], string='Pre-condition Type', default='none', required=True, help='Automatically set to T1 Must Be Closed when linked inbound records use T1.')
    pre_satisfied_date = fields.Datetime(string='Pre-condition Satisfied Date', readonly=True)
    pre_mrn_ids = fields.One2many('customs.file.pre.mrn', 'customs_file_id', string='Pre-condition MRNs', help='Automatically generated from linked inbound T1 gate arrivals.')
    t1_precondition_file_ids = fields.Many2many('bonded.customs.file', compute='_compute_t1_precondition_file_ids', string='Related T1 Customs Declarations')
    t1_closed_date = fields.Datetime(string='T1 Closed Date', readonly=True)
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
    declaration_attachment_line_ids = fields.Many2many('ir.attachment', 'bonded_customs_file_declaration_attachment_rel', 'customs_file_id', 'attachment_id', string='Declaration Attachments', copy=False)
    response_attachment_line_ids = fields.Many2many('ir.attachment', 'bonded_customs_file_response_attachment_rel', 'customs_file_id', 'attachment_id', string='Customs Response Attachments', copy=False)
    line_ids = fields.One2many('bonded.customs.file.line', 'customs_file_id', string='Declaration Lines')
    gate_arrival_ids = fields.One2many('gate.arrival', 'customs_file_id', string='Gate Arrivals',
                                       help='T1 only: container arrival records linked to this T1')
    inbound_ids = fields.Many2many('bonded.inbound', 'bonded_inbound_customs_file_rel', 'customs_file_id', 'bonded_inbound_id', string='Bonded Inbounds')
    outbound_ids = fields.One2many('bonded.outbound', 'customs_file_id', string='Bonded Outbounds')
    mrn_ids = fields.One2many('bonded.mrn', 'customs_file_id', string='MRN Numbers')
    remark = fields.Text(string='Remark')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    @api.depends('inbound_ids.gate_arrival_ids.customs_file_id')
    def _compute_t1_precondition_file_ids(self):
        for rec in self:
            rec.t1_precondition_file_ids = rec.inbound_ids.gate_arrival_ids.mapped('customs_file_id').filtered(
                lambda customs_file: customs_file.declaration_type == 't1_in'
            )

    _sql_constraints = [
        ('declaration_no_uniq', 'unique(declaration_no)', 'Declaration number must be unique!'),
    ]

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
                    'b3_in': 'seq.customs.file.b3_in',
                    'b3_out': 'seq.customs.file.b3_out',
                    't1_out': 'seq.customs.file.t1_out',
                    'ex': 'seq.customs.file.ex',
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
        return result

    def unlink(self):
        for rec in self:
            if rec.declaration_no and rec.declaration_no != _('New'):
                raise UserError(_('Customs declaration with a generated number cannot be deleted. Please cancel it instead.'))
        return super().unlink()

    @api.constrains('mrn')
    def check_mrn(self):
        pattern = re.compile(r'^\d{2}[A-Z]{2}[A-Z0-9]{14}$')
        for rec in self:
            if rec.mrn and not pattern.match(rec.mrn):
                raise ValidationError(_('MRN must be 18 characters: 2 digits + 2 letters + 14 letters/digits.'))

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
            if not rec.line_ids:
                raise UserError(_('Please add declaration lines before submitting.'))
            rec.validate_eori_parties()
            if rec.declaration_type in ('t1_in', 't1_out') and not rec.mrn:
                raise UserError(_('T1 declarations require an MRN before submission.'))
            if rec.declaration_type == 'b3_in':
                inbound_records = self.env['bonded.inbound'].sudo().search([('customs_file_ids', 'in', rec.ids)])
                inbound_t1_mrn_ids = set()
                rec.pre_mrn_ids.ensure_mrn_id()
                b3_pre_mrn_ids = set(rec.pre_mrn_ids.mapped('mrn_id').ids)
                has_t1_source = False
                for inbound in inbound_records:
                    if inbound.cargo_source == 'direct':
                        if inbound.t1_customs_file_id or inbound.gate_arrival_ids:
                            raise UserError(_('Direct entry cannot have T1 customs file or gate arrivals.'))
                        continue
                    has_t1_source = True
                    if not inbound.gate_arrival_ids:
                        raise UserError(_('T1 cargo source requires at least one gate arrival record.'))
                    for arrival in inbound.gate_arrival_ids:
                        t1_file = arrival.customs_file_id
                        if not t1_file or t1_file.declaration_type != 't1_in' or not arrival.mrn:
                            raise UserError(_('Every gate arrival must be linked to a T1 declaration with an MRN.'))
                        t1_file.ensure_mrn_record()
                        inbound_t1_mrn_ids.add(t1_file.mrn_id.id)
                if has_t1_source and rec.pre_condition != 't1_closed':
                    rec.pre_condition = 't1_closed'
                if has_t1_source:
                    b3_pre_mrn_ids = set(rec.pre_mrn_ids.mapped('mrn_id').ids)
                    missing_mrn_ids = inbound_t1_mrn_ids - b3_pre_mrn_ids
                    if missing_mrn_ids:
                        self.env['customs.file.pre.mrn'].create([
                            {'customs_file_id': rec.id, 'mrn_id': mrn_id} for mrn_id in missing_mrn_ids
                        ])
                    b3_pre_mrn_ids |= missing_mrn_ids
                if rec.pre_mrn_ids and not inbound_t1_mrn_ids:
                    raise UserError(_('Direct entry B3 cannot have pre-condition MRNs.'))
                if inbound_t1_mrn_ids - b3_pre_mrn_ids:
                    raise UserError(_('B3 pre-condition MRNs must include every inbound T1 MRN.'))
            if rec.declaration_type == 'b3_in' and rec.pre_condition == 't1_closed':
                if not rec.pre_mrn_ids:
                    raise UserError(_('T1 inbound scenario requires at least one pre-condition MRN.'))
                open_mrns = rec.pre_mrn_ids.filtered(lambda mrn: mrn.status != 'closed')
                if open_mrns:
                    raise UserError(_('The following T1 MRN(s) have not been closed: %s') % ', '.join(open_mrns.mapped('mrn')))
                rec.pre_satisfied_date = fields.Datetime.now()
                # ---- 货值校验 ----
            if not rec.check_value_limit():
                raise UserError(_('Value limit check failed. Please verify bonded.value.limit.'))
            # ---- 商品备案校验 ----
            if not rec.check_product_filing():
                raise UserError(_('Product filing check failed. Please verify bonded.product records.'))
            rec.write({'state': 'submitted', 'declaration_date': fields.Datetime.now()})
            rec.sync_instruction_state('declared')

    def action_approve(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_('Only submitted declarations can be approved.'))
            rec.write({
                'state': 'customs_approved',
                'approval_date': fields.Datetime.now(),
                'approval_no': self.env['ir.sequence'].next_by_code('seq.customs.approval') or 'APP-' + fields.Datetime.now().strftime('%Y%m%d%H%M%S'),
            })
            if rec.declaration_type == 'b3_in':
                inbound_records = self.env['bonded.inbound'].sudo().search([('customs_file_ids', 'in', rec.ids)])
                for inbound in inbound_records:
                    bonded_book = self.env['bonded.book'].browse(inbound.bonded_book_id.id)
                    bonded_book.deduct_document_value(project_id=inbound.project_id.id, inbound_id=inbound.id, customs_file_id=rec.id)
            elif rec.declaration_type in ('b3_out', 't1_out', 'ex', 'destruction'):
                outbound_records = self.env['bonded.outbound'].sudo().search([('customs_file_id', '=', rec.id)])
                for outbound in outbound_records:
                    bonded_book = self.env['bonded.book'].browse(outbound.bonded_book_id.id)
                    bonded_book.deduct_document_value(project_id=outbound.project_id.id, outbound_id=outbound.id, customs_file_id=rec.id)
            rec.sync_instruction_state('released')

    def action_reject(self, reason=''):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_('Only submitted declarations can be rejected.'))
            rec.write({'state': 'customs_rejected', 'rejection_reason': reason or _('Rejected by customs authority.')})
            inbound_records = self.env['bonded.inbound'].sudo().search([('customs_file_ids', 'in', rec.ids)])
            for inbound in inbound_records:
                bonded_book = self.env['bonded.book'].browse(inbound.bonded_book_id.id)
                bonded_book.release_document_value(project_id=inbound.project_id.id, inbound_id=inbound.id, customs_file_id=rec.id)
            outbound_records = self.env['bonded.outbound'].sudo().search([('customs_file_id', '=', rec.id)])
            for outbound in outbound_records:
                bonded_book = self.env['bonded.book'].browse(outbound.bonded_book_id.id)
                bonded_book.release_document_value(project_id=outbound.project_id.id, outbound_id=outbound.id, customs_file_id=rec.id)
            # T1出库驳回: 自动解锁库存(Fix-2)
            if rec.declaration_type == 'b3_in':
                rec.reset_inbound_on_rejection()
            elif rec.declaration_type in ('b3_out', 't1_out', 'ex', 'destruction'):
                rec.unlock_stock_on_rejection()

    def action_done(self):
        """T1核销闭环 / B3完成"""
        for rec in self:
            if rec.state != 'customs_approved':
                raise UserError(_('Only approved declarations can be set to done.'))
            if rec.declaration_type == 't1_in' and not rec.gate_arrival_ids:
                raise UserError(_('T1 declaration requires at least one gate arrival before it can be completed.'))
            rec.write({'state': 'done'})
            if rec.declaration_type == 't1_in':
                closed_date = fields.Datetime.now()
                rec.write({'t1_closed_date': closed_date})
                rec.gate_arrival_ids.write({'state': 'closed', 't1_closed_date': closed_date})
                rec.ensure_mrn_record()
                pre_mrn_ids = self.env['customs.file.pre.mrn'].sudo().search([('mrn', '=', rec.mrn)]).ids
                pre_mrn_records = self.env['customs.file.pre.mrn'].browse(pre_mrn_ids)
                pre_mrn_records.ensure_mrn_id()
                pre_mrn_records.filtered(lambda pre_mrn: pre_mrn.mrn_id == rec.mrn_id).write({'status': 'closed', 'satisfied_date': closed_date})

    def action_cancel(self):
        for rec in self:
            if rec.state not in ('draft', 'to_be_submitted', 'submitted'):
                raise UserError(_('Only draft/to_submit/submitted declarations can be cancelled.'))
            rec.write({'state': 'cancelled'})

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
                    raise UserError(_('%s is required and must be a valid EORI number.') % label)
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
            if rec.declaration_type == 'b3_in':
                inbounds = self.env['bonded.inbound'].sudo().search([('customs_file_ids', 'in', rec.ids)])
                if not inbounds:
                    raise UserError(
                        _('Please create and link a bonded inbound instruction before submitting this declaration.'))
                invalid_inbounds = inbounds.filtered(
                    lambda inbound: inbound.state not in ('confirmed', 'declared', 'released'))
                if invalid_inbounds:
                    raise UserError(
                        _('Please confirm linked inbound instructions before submitting customs declaration.'))
                if target_state == 'declared':
                    ready_inbounds = inbounds.filtered(lambda inbound: all(customs_file.state in ('submitted', 'customs_approved', 'done') for customs_file in inbound.customs_file_ids))
                    ready_inbounds.filtered(lambda inbound: inbound.state == 'confirmed').write({'state': 'declared'})
                elif target_state == 'released':
                    ready_inbounds = inbounds.filtered(lambda inbound: all(customs_file.state in ('customs_approved', 'done') for customs_file in inbound.customs_file_ids))
                    ready_inbounds.filtered(lambda inbound: inbound.state in ('confirmed', 'declared')).write({'state': 'released'})

            elif rec.declaration_type in ('b3_out', 't1_out', 'ex', 'destruction'):
                outbound_ids = self.env['bonded.outbound'].sudo().search([('customs_file_id', '=', rec.id)]).ids
                if not outbound_ids:
                    raise UserError(
                        _('Please create and link a bonded outbound instruction before submitting this declaration.'))

                outbounds = self.env['bonded.outbound'].browse(outbound_ids)
                invalid_outbounds = outbounds.filtered(
                    lambda outbound: outbound.state not in ('confirmed', 'declared', 'released'))
                if invalid_outbounds:
                    raise UserError(
                        _('Please confirm linked outbound instructions before submitting customs declaration.'))
                outbounds.write({'state': target_state})
#入库报关被拒绝
    def reset_inbound_on_rejection(self):
        for rec in self:
            inbound_ids = self.env['bonded.inbound'].sudo().search([
                ('customs_file_ids', 'in', rec.ids),
                ('state', 'in', ('declared', 'released')),
            ])
            for inbound in inbound_ids:
                inbound.write({'state': 'confirmed'})


    def unlock_stock_on_rejection(self):
        """T1和B3出库申报驳回时，一键解锁所有因该申报被锁定的保税库存(Fix-2)"""
        self.ensure_one()
        outbound_ids = self.env['bonded.outbound'].sudo().search([('customs_file_id', '=', self.id)]).ids
        for outbound in self.env['bonded.outbound'].browse(outbound_ids):
            outbound.line_ids.mapped('bonded_stock_id').write({'locked': False})
            if outbound.state in ('draft', 'confirmed', 'declared', 'released'):
                outbound.write({'state': 'cancelled'})

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
