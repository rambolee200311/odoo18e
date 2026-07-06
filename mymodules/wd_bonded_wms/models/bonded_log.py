# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class BondedLog(models.Model):
    _name = 'bonded.log'
    _description = 'Bonded Operations Log - 保税监管日志(不可篡改)'
    _order = 'operation_time desc, id desc'
    _log_access = False  # 禁止自动记录create/write时间戳(该表本身应不可修改)

    user_id = fields.Many2one('res.users', string='Operator', required=True,
                              default=lambda self: self.env.user)
    operation_time = fields.Datetime(string='Operation Time', required=True,
                                     default=fields.Datetime.now)
    ip_address = fields.Char(string='IP Address')
    device_info = fields.Char(string='Device Info')
    mrn = fields.Char(string='MRN', index=True)
    model_name = fields.Char(string='Model', required=True, index=True)
    res_id = fields.Integer(string='Record ID', required=True, index=True)
    operation_type = fields.Char(string='Operation Type', required=True)
    operation_detail = fields.Text(string='Operation Detail',
                                   help='JSON format with before/after values')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('operation_time'):
                vals['operation_time'] = fields.Datetime.now()
            if not vals.get('user_id'):
                vals['user_id'] = self.env.user.id
        return super().create(vals_list)

    def unlink(self):
        raise models.UserError(_('Bonded log records cannot be deleted!'))