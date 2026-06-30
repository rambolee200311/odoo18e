import uuid

from odoo import api, fields, models


class S3OperationLog(models.Model):
    _name = 's3.operation.log'
    _description = 'S3 Operation Log'
    _order = 'id desc'

    log_code = fields.Char(string='Log Code', readonly=True, default=lambda self: uuid.uuid4().hex, index=True)
    user_id = fields.Many2one('res.users', string='User', readonly=True, index=True)
    user_name = fields.Char(string='User Name', readonly=True, index=True)
    operate_time = fields.Datetime(string='Operate Time', readonly=True, default=fields.Datetime.now, index=True)
    operate_type_id = fields.Many2one('s3.operate.type', string='Operate Type', index=True)
    file_name = fields.Char(string='File Name', readonly=True, index=True)
    file_path = fields.Char(string='File Path', readonly=True, index=True)
    original_path = fields.Char(string='Original Path', readonly=True)
    operate_result = fields.Selection([('success', 'Success'), ('fail', 'Fail')], string='Operate Result', readonly=True, default='success', index=True)
    error_message = fields.Text(string='Error Message', readonly=True)
    delete_reason = fields.Char(string='Delete Reason', readonly=True)
    clean_reason = fields.Char(string='Clean Reason', readonly=True)

    _sql_constraints = [
        ('s3_operation_log_code_unique', 'unique(log_code)', 'Log code must be unique.'),
    ]

    @api.model
    def create_log_line(self, vals):
        value_data = dict(vals or {})
        user_model = self.env['res.users'].sudo()
        user = user_model.browse(value_data.get('user_id') or self.env.uid)
        value_data.setdefault('user_id', user.id)
        value_data.setdefault('user_name', user.name)
        value_data.setdefault('operate_time', fields.Datetime.now())
        return self.create(value_data)