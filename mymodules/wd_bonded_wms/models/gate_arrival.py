# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class GateArrival(models.Model):
    _name = 'gate.arrival'
    _description = 'Gate Arrival - 到仓登记(封志核验)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'arrival_datetime desc'

    name = fields.Char(string='Gate Arrival No.', required=True, copy=False,
                       default=lambda self: _('New'), readonly=True, index=True)
    customs_file_id = fields.Many2one('bonded.customs.file', string='T1 Customs Declaration',
                                      required=True,
                                      domain=[('declaration_type', 'in', ('t1_in',))],
                                      ondelete='restrict', index=True)
    mrn = fields.Char(string='MRN Number', related='customs_file_id.mrn', readonly=True, store=True)

    # 集装箱与封志
    container_no = fields.Char(string='Container Number')
    seal_no = fields.Char(string='Seal Number', required=True)
    seal_intact = fields.Boolean(string='Seal Intact', default=True, tracking=True)
    seal_confirmed = fields.Boolean(string='Seal Confirmed', default=False, readonly=True, tracking=True)
    seal_confirm_datetime = fields.Datetime(string='Seal Confirmation Time', readonly=True, copy=False)
    seal_attachment_line_ids = fields.Many2many('ir.attachment', 'gate_arrival_seal_attachment_rel', 'gate_arrival_id', 'attachment_id', string='Seal Attachments', copy=False)

    # POD
    pod_attachment_line_ids = fields.Many2many('ir.attachment', 'gate_arrival_pod_attachment_rel', 'gate_arrival_id', 'attachment_id', string='POD Attachments', copy=False)

    # 运输信息
    carrier_id = fields.Many2one('res.partner', string='Carrier', required=True)
    plate_number = fields.Char(string='Truck Plate Number')
    driver_name = fields.Char(string='Driver Name')
    driver_phone = fields.Char(string='Driver Phone')
    arrival_datetime = fields.Datetime(string='Arrival Time', required=True)

    charge_lines = fields.One2many('bonded.charge.line', 'gate_arrival_id', string='Charge Lines')

    # 状态
    state = fields.Selection([
        ('pending', 'Pending T1 Closure'),
        ('closed', 'T1 Closed'),
    ], string='Status', default='pending', required=True, tracking=True)
    t1_closed_date = fields.Datetime(string='T1 Closed Date', readonly=True)

    # 关联入库指令 (每条到仓登记只属于一个入库单)
    bonded_inbound_id = fields.Many2one('bonded.inbound', string='Bonded Inbound', required=True,
                                        ondelete='restrict', index=True)
    inbound_tracking_no = fields.Char(string='Inbound Tracking No.', related='bonded_inbound_id.inbound_tracking_id.name', readonly=True, store=True, index=True)

    remark = fields.Text(string='Remark')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        customs_file_id = vals.get('customs_file_id') or self.env.context.get('default_customs_file_id')
        if customs_file_id and not vals.get('bonded_inbound_id'):
            customs_file = self.env['bonded.customs.file'].sudo().browse(customs_file_id).exists()
            if len(customs_file.inbound_ids) == 1:
                vals['bonded_inbound_id'] = customs_file.inbound_ids.id
        return vals

    @api.constrains('customs_file_id', 'bonded_inbound_id')
    def check_inbound_link(self):
        for rec in self:
            duplicate_arrival = self.env['gate.arrival'].sudo().search([('customs_file_id', '=', rec.customs_file_id.id), ('id', '!=', rec.id)], limit=1)
            if duplicate_arrival:
                raise ValidationError(_('A T1 customs declaration can only have one gate arrival.'))
            duplicate_inbound_arrival = self.env['gate.arrival'].sudo().search([('bonded_inbound_id', '=', rec.bonded_inbound_id.id), ('id', '!=', rec.id)], limit=1)
            if duplicate_inbound_arrival:
                raise ValidationError(_('An inbound instruction can only have one gate arrival.'))
            if rec.customs_file_id and rec.customs_file_id.declaration_type != 't1_in':
                raise ValidationError(_('Gate arrival must be linked to a T1 customs declaration.'))
            if rec.customs_file_id and rec.customs_file_id.state == 'done':
                raise ValidationError(_('Gate arrival cannot be added after the T1 customs declaration is completed.'))
            if rec.customs_file_id and rec.bonded_inbound_id and rec.customs_file_id.bonded_book_id != rec.bonded_inbound_id.bonded_book_id:
                raise ValidationError(_('The T1 customs declaration and bonded inbound must use the same bonded book.'))
            if rec.customs_file_id and rec.bonded_inbound_id and rec.customs_file_id != rec.bonded_inbound_id.t1_customs_file_id:
                raise ValidationError(_('The gate arrival must use the inbound instruction T1 customs declaration.'))

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Gate arrival number must be unique!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('customs_file_id') and not vals.get('bonded_inbound_id'):
                customs_file = self.env['bonded.customs.file'].sudo().browse(vals['customs_file_id']).exists()
                if len(customs_file.inbound_ids) == 1:
                    vals['bonded_inbound_id'] = customs_file.inbound_ids.id
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('seq.gate.arrival') or _('New')
        return super().create(vals_list)

    def action_confirm_seal_intact(self):
        """确认封志完好"""
        for rec in self:
            if rec.seal_confirmed:
                continue
            if not rec.seal_intact:
                raise UserError(_('A damaged seal cannot be confirmed as intact.'))
            if not rec.seal_attachment_line_ids:
                raise UserError(_('Please upload seal attachments before confirming seal is intact.'))
            rec.write({'seal_confirmed': True, 'seal_confirm_datetime': fields.Datetime.now()})

    def action_report_seal_damaged(self):
        """报告封志损坏"""
        self.ensure_one()
        self.seal_intact = False
        # 触发T1异常流程
        self.customs_file_id.message_post(
            body=_('Seal damaged reported for container %s (seal no: %s). T1 abnormal flow triggered.')
                  % (self.container_no, self.seal_no),
            subtype_id=self.env.ref('mail.mt_note').id,
        )
