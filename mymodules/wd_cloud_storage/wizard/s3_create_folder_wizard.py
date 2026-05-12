from odoo import api, fields, models
from odoo.exceptions import UserError


class S3CreateFolderWizard(models.TransientModel):
    _name = 's3.create.folder.wizard'
    _description = 'S3 Create Folder Wizard'
    _order = 'id desc'

    node_id = fields.Many2one('s3.node', string='Parent Folder', required=True, readonly=True, index=True)
    folder_name = fields.Char(string='Name', required=True)

    @api.model
    def default_get(self, field_list):
        vals = super().default_get(field_list)
        node_id = self.env.context.get('default_node_id')
        if node_id:
            self.env['s3.node'].check_can_create_subfolder_in_node(node_id)
            vals['node_id'] = node_id
        return vals

    def action_confirm(self):
        for rec in self:
            folder_name = (rec.folder_name or '').strip()
            if not folder_name:
                raise UserError('Folder name is required.')
            self.env['s3.node'].create_subfolder_in_node(rec.node_id.id, folder_name)
        return {'type': 'ir.actions.act_window_close'}
