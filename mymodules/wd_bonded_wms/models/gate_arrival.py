# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


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

    # 反向关联pre.mrn中间表 (一个集装箱唯一归属一个T1 MRN)
    pre_mrn_t1_id = fields.Many2one('customs.file.pre.mrn', string='Pre-condition MRN Link',
                                    help='Each container belongs to exactly one T1 MRN')

    # 货代换单关联
    handover_id = fields.Many2one('operation.order.handover', string='Handover',
                                  help='Import handover, auto-brings DO/container/seal info')

    # 集装箱与封志
    container_no = fields.Char(string='Container Number', required=True)
    seal_no = fields.Char(string='Seal Number', required=True)
    seal_intact = fields.Boolean(string='Seal Intact', default=True, tracking=True)
    seal_attachment_line_ids = fields.Many2many('ir.attachment', 'gate_arrival_seal_attachment_rel', 'gate_arrival_id', 'attachment_id', string='Seal Attachments', copy=False)

    # POD
    pod_attachment_line_ids = fields.Many2many('ir.attachment', 'gate_arrival_pod_attachment_rel', 'gate_arrival_id', 'attachment_id', string='POD Attachments', copy=False)

    # 运输信息
    carrier_id = fields.Many2one('res.partner', string='Carrier', required=True)
    plate_number = fields.Char(string='Truck Plate Number')
    driver_name = fields.Char(string='Driver Name')
    driver_phone = fields.Char(string='Driver Phone')
    arrival_datetime = fields.Datetime(string='Arrival Time', required=True)

    # 费用分摊(R1)
    charge_line_ids = fields.One2many('world.depot.inbound.order.charge', 'gate_arrival_id', string='Allocated Charges',
                                      help='Charges allocated to this gate arrival (for cost splitting)')

    # 状态
    state = fields.Selection([
        ('pending', 'Pending T1 Closure'),
        ('closed', 'T1 Closed'),
    ], string='Status', default='pending', required=True, tracking=True)
    t1_closed_date = fields.Datetime(string='T1 Closed Date', readonly=True)

    # 关联入库指令 (每条到仓登记只属于一个入库单)
    bonded_inbound_id = fields.Many2one('bonded.inbound', string='Bonded Inbound', required=True,
                                        ondelete='restrict', index=True)
    inbound_tracking_no = fields.Char(string='Inbound Tracking No.', related='bonded_inbound_id.inbound_tracking_no', readonly=True, store=True, index=True)

    remark = fields.Text(string='Remark')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    @api.constrains('customs_file_id', 'bonded_inbound_id')
    def check_inbound_link(self):
        for rec in self:
            if rec.customs_file_id and rec.customs_file_id.declaration_type != 't1_in':
                raise ValidationError(_('Gate arrival must be linked to a T1 customs declaration.'))
            if rec.bonded_inbound_id and rec.bonded_inbound_id.cargo_source == 'direct':
                raise ValidationError(_('Direct entry inbound cannot have a gate arrival.'))
            if rec.customs_file_id and rec.bonded_inbound_id and rec.customs_file_id.bonded_book_id != rec.bonded_inbound_id.bonded_book_id:
                raise ValidationError(_('The T1 customs declaration and bonded inbound must use the same bonded book.'))

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Gate arrival number must be unique!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('seq.gate.arrival') or _('New')
        return super().create(vals_list)

    def action_confirm_seal_intact(self):
        """确认封志完好"""
        for rec in self:
            if not rec.seal_attachment_line_ids:
                raise UserError(_('Please upload seal attachments before confirming seal is intact.'))
            rec.write({'seal_intact': True})

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
