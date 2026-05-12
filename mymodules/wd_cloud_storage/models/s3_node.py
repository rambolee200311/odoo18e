from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
import re

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
        node_model_sudo = self.env['s3.node'].sudo()
        for vals in vals_list:
            if vals.get('s3_key'):
                vals['s3_key'] = vals['s3_key'].strip()
            if vals.get('s3_key') == '':
                raise ValidationError('S3 key cannot be empty.')
            if vals.get('parent_id') and not vals.get('user_id'):
                parent = node_model_sudo.browse(vals['parent_id'])
                if parent and parent.user_id:
                    vals['user_id'] = parent.user_id.id
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

    # 一键初始化部门文件夹和管理员文件夹具体方法
    @api.model
    def action_init_public_folders(self):
        if not self.env.user.has_group('wd_cloud_storage.group_wd_cloud_storage_admin'):
            raise AccessError('Only cloud storage admin can initialize public folders.')

        node_type_model = self.env['s3.node.type'].sudo()
        node_model_sudo = self.env['s3.node'].sudo()
        permission_model_sudo = self.env['s3.permission'].sudo()
        department_model = self.env['hr.department'].sudo()

        public_type = node_type_model.search([('code', '=', 'public'), ('is_active', '=', True)], limit=1,
                                             order='id desc')
        if not public_type:
            raise UserError('Public node type not found.')

        base_nodes = self.ensure_base_nodes()
        public_root = self.browse(base_nodes['public'])
        public_prefix = public_root.s3_key if public_root.s3_key.endswith('/') else f"{public_root.s3_key}/"

        def ensure_node(folder_name, folder_key):
            node = node_model_sudo.search([
                ('node_type_id', '=', public_type.id),
                ('parent_id', '=', public_root.id),
                ('s3_key', '=', folder_key),
                ('company_id', '=', self.env.company.id),
            ], limit=1, order='id desc')
            if node:
                return self.browse(node.id)
            return self.env['s3.node'].create({
                'name': folder_name,
                'node_type_id': public_type.id,
                'parent_id': public_root.id,
                's3_key': folder_key,
                'company_id': self.env.company.id,
            })

        def ensure_permission(node, grantee_type, permission_level, user_id=False, group_id=False, department_id=False):
            domain = [
                ('node_id', '=', node.id),
                ('grantee_type', '=', grantee_type),
                ('user_id', '=', user_id or False),
                ('group_id', '=', group_id or False),
                ('department_id', '=', department_id or False),
            ]
            existed = permission_model_sudo.search(domain, limit=1, order='id desc')
            if existed:
                if existed.permission_level != permission_level:
                    self.env['s3.permission'].browse(existed.id).write({'permission_level': permission_level})
                return
            self.env['s3.permission'].create({
                'node_id': node.id,
                'grantee_type': grantee_type,
                'permission_level': permission_level,
                'user_id': user_id or False,
                'group_id': group_id or False,
                'department_id': department_id or False,
            })



        all_read_node = ensure_node('All Read', f'{public_prefix}all-read/')
        admin_only_node = ensure_node('Admin Only', f'{public_prefix}admin-only/')

        group_user = self.env.ref('base.group_user')
        group_admin = self.env.ref('wd_cloud_storage.group_wd_cloud_storage_admin')

        ensure_permission(public_root, 'group', 'read', group_id=group_user.id)
        ensure_permission(public_root, 'group', 'full_control', group_id=group_admin.id)
        ensure_permission(all_read_node, 'group', 'read', group_id=group_user.id)
        ensure_permission(admin_only_node, 'group', 'full_control', group_id=group_admin.id)

        departments = department_model.search(
            ['|', ('company_id', '=', False), ('company_id', '=', self.env.company.id)],
            order='id desc'
        )
        for dep in departments:
            dep_node = ensure_node(f'Department - {dep.name}', f'{public_prefix}department-{dep.id}/')
            ensure_permission(dep_node, 'department', 'write', department_id=dep.id)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': 'Success',
                'message': 'Public folders and permissions initialized.',
                'sticky': False,
            },
        }

    @api.model
    def get_selected_node(self, node_id):
        node_model_sudo = self.env['s3.node'].sudo()
        node = node_model_sudo.search(
            [('id', '=', node_id), ('is_active', '=', True), ('company_id', '=', self.env.company.id)],
            limit=1, order='id desc'
        )
        if not node:
            raise UserError('Please select a valid folder first.')
        return self.env['s3.node'].browse(node.id)

    @api.model
    def check_can_upload_in_node(self, node_id):
        node = self.get_selected_node(node_id)
        node.check_access_for_user(action_name='write')
        if node.node_type_id.code in ('recycle_root', 'recycle_bin'):
            raise UserError('Recycle folder does not allow upload.')
        return True

    @api.model
    def check_can_create_subfolder_in_node(self, node_id):
        node = self.get_selected_node(node_id)
        node.check_access_for_user(action_name='write')
        if node.node_type_id.code in ('root', 'recycle_root', 'recycle_bin'):
            raise UserError('This folder does not allow subfolder creation.')
        if node.node_type_id.code not in ('private_root', 'private_sub'):
            raise UserError('Only personal folder supports subfolder creation.')
        if not node.user_id or node.user_id.id != self.env.uid:
            raise AccessError('You can only create subfolder in your own personal folder.')
        return True

    @api.model
    def create_subfolder_in_node(self, node_id, folder_name):
        node = self.get_selected_node(node_id)
        self.check_can_create_subfolder_in_node(node.id)

        folder_name_text = (folder_name or '').strip()
        if not folder_name_text:
            raise UserError('Folder name is required.')

        safe_key_name = re.sub(r'[^A-Za-z0-9._-]+', '-', folder_name_text).strip('-').lower() or 'folder'
        parent_key = node.s3_key if node.s3_key.endswith('/') else f'{node.s3_key}/'
        folder_key = f'{parent_key}{safe_key_name}/'

        node_model_sudo = self.env['s3.node'].sudo()
        seq = 1
        while node_model_sudo.search_count([('s3_key', '=', folder_key), ('company_id', '=', self.env.company.id)]):
            folder_key = f'{parent_key}{safe_key_name}-{seq}/'
            seq += 1

        node_type_model_sudo = self.env['s3.node.type'].sudo()
        private_sub_type = node_type_model_sudo.search(
            [('code', '=', 'private_sub'), ('is_active', '=', True)],
            limit=1, order='id desc'
        )
        if not private_sub_type:
            raise UserError('Private subfolder type not found.')

        new_node = self.env['s3.node'].create({
            'name': folder_name_text,
            'node_type_id': private_sub_type.id,
            's3_key': folder_key,
            'parent_id': node.id,
            'user_id': self.env.uid,
            'company_id': self.env.company.id,
            'is_active': True,
        })
        return {'id': new_node.id, 'name': new_node.name}