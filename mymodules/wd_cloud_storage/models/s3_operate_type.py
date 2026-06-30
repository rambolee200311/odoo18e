from odoo import fields, models


class S3OperateType(models.Model):
    _name = 's3.operate.type'
    _description = 'S3 Operate Type'
    _order = 'id desc'

    name = fields.Char(string='Name', required=True, index=True)
    code = fields.Char(string='Code', required=True, index=True)
    description = fields.Char(string='Description')
    is_active = fields.Boolean(string='Active', default=True, index=True)

    _sql_constraints = [
        ('s3_operate_type_code_unique', 'unique(code)', 'Operate type code must be unique.'),
    ]