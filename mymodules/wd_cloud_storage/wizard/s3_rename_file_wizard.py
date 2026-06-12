from odoo import api, fields, models
from odoo.exceptions import UserError


class S3RenameFileWizard(models.TransientModel):
    _name = 's3.rename.file.wizard'
    _description = 'S3 Rename File Wizard'
    _order = 'id desc'

    file_id = fields.Many2one('s3.stored.file', string='File', required=True, readonly=True, index=True)
    new_name = fields.Char(string='Name', required=True)

    @api.model
    def default_get(self, field_list):
        vals = super().default_get(field_list)
        file_id = self.env.context.get('default_file_id')
        if file_id:
            file_model_sudo = self.env['s3.stored.file'].sudo()
            file_sudo = file_model_sudo.search([('id', '=', file_id), ('is_active', '=', True)], limit=1, order='id desc')
            if not file_sudo:
                raise UserError('File does not exist.')
            file_record = self.env['s3.stored.file'].browse(file_sudo.id)
            file_record.check_node_access('rename')
            if file_sudo.state != 'stored':
                raise UserError('Only stored file can be renamed.')
            vals['file_id'] = file_sudo.id
            vals['new_name'] = file_sudo.name
        return vals

    def action_confirm(self):
        for rec in self:
            new_name = (rec.new_name or '').strip()
            if not new_name:
                raise UserError('File name is required.')
            rec.file_id.action_rename_file(new_name)
        return {'type': 'ir.actions.act_window_close'}