from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class S3Node(models.Model):
    _name = 's3.node'
    _description = 'S3 Node'
    _order = 'id desc'

    name = fields.Char(string='Name', required=True, index=True)
    node_type_id = fields.Many2one('s3.node.type', string='Node Type', required=True, ondelete='restrict', index=True)
    s3_key = fields.Char(string='S3 Key', required=True, index=True)
    parent_id = fields.Many2one('s3.node', string='Parent Node', ondelete='cascade', index=True)
    child_lines = fields.One2many('s3.node', 'parent_id', string='Child Nodes')
    user_id = fields.Many2one('res.users', string='Owner User', index=True)
    permission_lines = fields.One2many('s3.permission', 'node_id', string='Permission Lines')
    file_lines = fields.One2many('s3.stored.file', 'node_id', string='File Lines')
    is_active = fields.Boolean(string='Active', default=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company, index=True, readonly=True)
    description = fields.Char(string='Description')

    _sql_constraints = [
        ('s3_node_key_unique', 'unique(s3_key)', 'S3 key must be unique.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('s3_key'):
                vals['s3_key'] = vals['s3_key'].strip()
            if vals.get('s3_key') == '':
                raise ValidationError('S3 key cannot be empty.')
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('s3_key'):
            vals['s3_key'] = vals['s3_key'].strip()
            if not vals['s3_key']:
                raise ValidationError('S3 key cannot be empty.')
        for rec in self:
            if vals.get('parent_id') and vals.get('parent_id') == rec.id:
                raise ValidationError('Parent node cannot be itself.')
        return super().write(vals)

    @api.model
    def get_node_type_by_code(self, code):
        node_type_model = self.env['s3.node.type'].sudo()
        node_type = node_type_model.search([('code', '=', code), ('is_active', '=', True)], limit=1, order='id desc')
        return self.env['s3.node.type'].browse(node_type.id) if node_type else self.env['s3.node.type']

    @api.model
    def ensure_base_nodes(self):
        config_model = self.env['s3.config']
        config = config_model.get_current_config()
        node_model_sudo = self.env['s3.node'].sudo()
        node_model = self.env['s3.node']
        root_type = self.get_node_type_by_code('root')
        public_type = self.get_node_type_by_code('public')
        temp_type = self.get_node_type_by_code('temp')
        recycle_root_type = self.get_node_type_by_code('recycle_root')
        if not all([root_type, public_type, temp_type, recycle_root_type]):
            raise UserError('Please initialize node type data first.')
        root_node = node_model_sudo.search([('node_type_id', '=', root_type.id), ('s3_key', '=', '/'), ('company_id', '=', self.env.company.id)], limit=1, order='id desc')
        if not root_node:
            root_node = node_model.create({'name': 'Root', 'node_type_id': root_type.id, 's3_key': '/', 'company_id': self.env.company.id})
        public_node = node_model_sudo.search([('node_type_id', '=', public_type.id), ('s3_key', '=', config.prefix_public), ('company_id', '=', self.env.company.id)], limit=1, order='id desc')
        if not public_node:
            public_node = node_model.create({'name': 'Public', 'node_type_id': public_type.id, 's3_key': config.prefix_public, 'parent_id': root_node.id, 'company_id': self.env.company.id})
        temp_node = node_model_sudo.search([('node_type_id', '=', temp_type.id), ('s3_key', '=', config.prefix_temp), ('company_id', '=', self.env.company.id)], limit=1, order='id desc')
        if not temp_node:
            temp_node = node_model.create({'name': 'Temp', 'node_type_id': temp_type.id, 's3_key': config.prefix_temp, 'parent_id': root_node.id, 'company_id': self.env.company.id})
        recycle_root_node = node_model_sudo.search([('node_type_id', '=', recycle_root_type.id), ('s3_key', '=', config.prefix_recycle), ('company_id', '=', self.env.company.id)], limit=1, order='id desc')
        if not recycle_root_node:
            recycle_root_node = node_model.create({'name': 'Recycle', 'node_type_id': recycle_root_type.id, 's3_key': config.prefix_recycle, 'parent_id': root_node.id, 'company_id': self.env.company.id})
        return {'root': root_node.id, 'public': public_node.id, 'temp': temp_node.id, 'recycle_root': recycle_root_node.id}

    @api.model
    def ensure_private_node(self, user_id=False):
        user_model = self.env['res.users'].sudo()
        user = user_model.browse(user_id or self.env.uid).exists()
        if not user:
            raise UserError('User not found.')
        config_model = self.env['s3.config']
        config = config_model.get_current_config()
        base_nodes = self.ensure_base_nodes()
        node_model_sudo = self.env['s3.node'].sudo()
        node_model = self.env['s3.node']
        private_root_type = self.get_node_type_by_code('private_root')
        recycle_bin_type = self.get_node_type_by_code('recycle_bin')
        if not all([private_root_type, recycle_bin_type]):
            raise UserError('Please initialize private and recycle node type data first.')
        private_key = f"{config.prefix_private}user_{user.id}/"
        recycle_key = f"{config.prefix_recycle}user_{user.id}/"
        private_node = node_model_sudo.search([('node_type_id', '=', private_root_type.id), ('s3_key', '=', private_key), ('user_id', '=', user.id), ('company_id', '=', self.env.company.id)], limit=1, order='id desc')
        if not private_node:
            private_node = node_model.create({'name': f'Private {user.name}', 'node_type_id': private_root_type.id, 's3_key': private_key, 'user_id': user.id, 'parent_id': base_nodes['root'], 'company_id': self.env.company.id})
        recycle_node = node_model_sudo.search([('node_type_id', '=', recycle_bin_type.id), ('s3_key', '=', recycle_key), ('user_id', '=', user.id), ('company_id', '=', self.env.company.id)], limit=1, order='id desc')
        if not recycle_node:
            recycle_node = node_model.create({'name': f'Recycle {user.name}', 'node_type_id': recycle_bin_type.id, 's3_key': recycle_key, 'user_id': user.id, 'parent_id': base_nodes['recycle_root'], 'company_id': self.env.company.id})
        return {'private_node_id': private_node.id, 'recycle_node_id': recycle_node.id}

    def check_access_for_user(self, user_id=False, action_name='read', raise_error=True):
        user_model = self.env['res.users'].sudo()
        permission_model = self.env['s3.permission']
        user = user_model.browse(user_id or self.env.uid).exists()
        if not user:
            if raise_error:
                raise AccessError('User not found.')
            return False
        is_admin = user.has_group('wd_cloud_storage.group_wd_cloud_storage_admin')
        allowed = True
        for rec in self:
            node_code = rec.node_type_id.code
            node_allowed = False
            if is_admin:
                node_allowed = True
            elif node_code in ('root', 'temp', 'recycle_root') and action_name == 'read':
                node_allowed = True
            elif node_code in ('private_root', 'private_sub', 'recycle_bin') and rec.user_id and rec.user_id.id == user.id:
                node_allowed = True
            elif node_code == 'public':
                node_allowed = permission_model.check_permission_for_user(user.id, rec.id, action_name)
            if not node_allowed:
                allowed = False
                if raise_error:
                    raise AccessError('You do not have access permission for this node.')
        return allowed

    def get_authorized_children(self, action_name='read'):
        node_model_sudo = self.env['s3.node'].sudo()
        authorized_ids = []
        for rec in self:
            child_nodes = node_model_sudo.search([('parent_id', '=', rec.id), ('is_active', '=', True)], order='id desc')
            for child in child_nodes:
                if self.browse(child.id).check_access_for_user(action_name=action_name, raise_error=False):
                    authorized_ids.append(child.id)
        return self.browse(authorized_ids)

    def action_prepare_my_space(self):
        for rec in self:
            rec.ensure_private_node(self.env.uid)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': 'Success',
                'message': 'Your private node and recycle node are ready.',
                'sticky': False,
            },
        }