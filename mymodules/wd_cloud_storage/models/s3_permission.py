from odoo import api, fields, models
from odoo.exceptions import ValidationError


class S3Permission(models.Model):
    _name = 's3.permission'
    _description = 'S3 Permission'
    _order = 'id desc'

    node_id = fields.Many2one('s3.node', string='Node', required=True, ondelete='cascade', index=True)
    grantee_type = fields.Selection([('user', 'User'), ('group', 'Group'), ('department', 'Department')], string='Grantee Type', required=True, default='user', index=True)
    user_id = fields.Many2one('res.users', string='User', index=True)
    group_id = fields.Many2one('res.groups', string='Group', index=True)
    department_id = fields.Integer(string='Department Id', index=True)
    permission_level = fields.Selection([('read', 'Read'), ('write', 'Write'), ('full_control', 'Full Control')], string='Permission Level', required=True, default='read', index=True)
    granted_by_id = fields.Many2one('res.users', string='Granted By', default=lambda self: self.env.user, readonly=True, index=True)
    granted_datetime = fields.Datetime(string='Granted Datetime', default=fields.Datetime.now, readonly=True)

    @api.constrains('grantee_type', 'user_id', 'group_id', 'department_id')
    def check_grantee_target(self):
        for rec in self:
            if rec.grantee_type == 'user' and not rec.user_id:
                raise ValidationError('User is required when grantee type is user.')
            if rec.grantee_type == 'group' and not rec.group_id:
                raise ValidationError('Group is required when grantee type is group.')
            if rec.grantee_type == 'department' and not rec.department_id:
                raise ValidationError('Department is required when grantee type is department.')

    def get_level_by_action(self, action_name):
        if action_name in ('read', 'download', 'preview'):
            return ['read', 'write', 'full_control']
        if action_name in ('write', 'upload', 'rename', 'move'):
            return ['write', 'full_control']
        return ['full_control']

    @api.model
    def check_permission_for_user(self, user_id, node_id, action_name='read'):
        user_model = self.env['res.users'].sudo()
        permission_model = self.env['s3.permission'].sudo()
        user = user_model.browse(user_id).exists()
        if not user:
            return False
        if user.has_group('wd_cloud_storage.group_wd_cloud_storage_admin'):
            return True
        level_values = self.get_level_by_action(action_name)
        permission_lines = permission_model.search([('node_id', '=', node_id), ('permission_level', 'in', level_values)], order='id desc')
        user_group_ids = user.groups_id.ids
        department_id = False
        if 'employee_id' in user._fields and user.employee_id and 'department_id' in user.employee_id._fields and user.employee_id.department_id:
            department_id = user.employee_id.department_id.id
        for rec in permission_lines:
            if rec.grantee_type == 'user' and rec.user_id and rec.user_id.id == user.id:
                return True
            if rec.grantee_type == 'group' and rec.group_id and rec.group_id.id in user_group_ids:
                return True
            if rec.grantee_type == 'department' and rec.department_id and rec.department_id == department_id:
                return True
        return False