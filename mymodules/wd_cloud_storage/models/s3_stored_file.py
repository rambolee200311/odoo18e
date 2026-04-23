import base64
import binascii
import hashlib
import mimetypes
import re
import uuid
from urllib.parse import quote
try:
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:
    BotoCoreError = Exception
    ClientError = Exception

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class S3StoredFile(models.Model):
    _name = 's3.stored.file'
    _description = 'S3 Stored File'
    _order = 'id desc'

    name = fields.Char(string='File Name', index=True)
    node_id = fields.Many2one('s3.node', string='Node', required=True, ondelete='restrict', index=True)
    s3_key = fields.Char(string='S3 Key', readonly=True, index=True)
    size = fields.Integer(string='File Size', readonly=True)
    mimetype = fields.Char(string='Mimetype', readonly=True)
    owner_id = fields.Many2one('res.users', string='Owner', required=True, default=lambda self: self.env.user, readonly=True, index=True)
    checksum = fields.Char(string='Checksum', readonly=True, index=True)
    upload_datetime = fields.Datetime(string='Upload Datetime', default=fields.Datetime.now, readonly=True, index=True)
    is_active = fields.Boolean(string='Active', default=True, index=True)
    state = fields.Selection([('draft', 'Draft'), ('stored', 'Stored'), ('recycled', 'Recycled')], string='State', default='draft', required=True, readonly=True, index=True)
    upload_datas = fields.Binary(string='Upload File', attachment=False, copy=False)
    upload_filename = fields.Char(string='Upload Filename', copy=False)
    recycle_lines = fields.One2many('s3.recycle.entry', 'file_id', string='Recycle Lines')
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company, readonly=True, index=True)

    def decode_upload_data(self, upload_datas):
        payload = upload_datas.encode() if isinstance(upload_datas, str) else (upload_datas or b'')
        try:
            return base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError):
            return base64.b64decode(payload)

    def sanitize_file_name(self, file_name):
        cleaned_name = re.sub(r'[^A-Za-z0-9._-]', '_', (file_name or '').strip())
        return cleaned_name or 'file.bin'

    def build_unique_s3_key(self, node, file_name):
        safe_name = self.sanitize_file_name(file_name)
        unique_code = uuid.uuid4().hex
        return f"{node.s3_key}{fields.Date.today()}/{unique_code}/{safe_name}"

    def check_node_access(self, action_name='read'):
        for rec in self:
            if not rec.node_id.check_access_for_user(action_name=action_name, raise_error=False):
                raise AccessError('You do not have permission on this node.')

    def process_upload_data(self):
        config_model = self.env['s3.config']
        config = config_model.get_current_config()
        client = config_model.get_s3_client()
        log_model = self.env['s3.operation.log']
        operate_type_model = self.env['s3.operate.type'].sudo()
        upload_operate_type = operate_type_model.search([('code', '=', 'upload')], limit=1, order='id desc')
        for rec in self:
            if not rec.upload_datas:
                continue
            rec.check_node_access('write')
            file_name = rec.upload_filename or rec.name
            binary_data = rec.decode_upload_data(rec.upload_datas)
            if not binary_data:
                raise UserError('Upload file is empty.')
            file_mimetype = mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
            config_model.check_upload_rule(len(binary_data), file_name, file_mimetype)
            s3_key = rec.build_unique_s3_key(rec.node_id, file_name)
            try:
                client.put_object(Bucket=config.s3_bucket, Key=s3_key, Body=binary_data, ContentType=file_mimetype)
            except (BotoCoreError, ClientError) as error:
                log_model.create_log_line({'operate_type_id': upload_operate_type.id if upload_operate_type else False, 'file_name': file_name, 'file_path': s3_key, 'operate_result': 'fail', 'error_message': str(error)})
                raise UserError(f'Upload to S3 failed: {error}') from error
            rec.with_context(skip_upload_hook=True).write({'name': file_name, 's3_key': s3_key, 'size': len(binary_data),
                                                           'mimetype': file_mimetype, 'checksum': hashlib.sha1(binary_data).hexdigest(),
                                                           'state': 'stored', 'is_active': True, 'upload_datas': False, 'upload_filename': False})
            log_model.create_log_line({'operate_type_id': upload_operate_type.id if upload_operate_type else False, 'file_name': file_name,
                                       'file_path': s3_key, 'operate_result': 'success'})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.upload_datas:
                rec.process_upload_data()
        return records

    def write(self, vals):
        result = super().write(vals)
        if self.env.context.get('skip_upload_hook'):
            return result
        if 'upload_datas' in vals or 'upload_filename' in vals:
            for rec in self:
                if rec.upload_datas:
                    rec.process_upload_data()
        return result

    def unlink(self):
        for rec in self:
            if rec.state == 'stored':
                raise UserError('Please move file to recycle first.')
        return super().unlink()

    @api.model
    def create_from_upload(self, node_id, file_data, file_name):
        node_model = self.env['s3.node'].sudo()
        node = node_model.search([('id', '=', node_id), ('is_active', '=', True)], limit=1, order='id desc')
        if not node:
            raise UserError('Node does not exist.')
        if not self.env['s3.node'].browse(node.id).check_access_for_user(action_name='write', raise_error=False):
            raise AccessError('You do not have write permission on this node.')
        file_record = self.create({'name': file_name or 'file.bin', 'node_id': node.id, 'upload_datas': file_data, 'upload_filename': file_name})
        return {'id': file_record.id, 'name': file_record.name}

    @api.model
    def get_paginated_files(self, node_id, page=1, limit=20, search=None):
        node_model = self.env['s3.node'].sudo()
        node = node_model.search([('id', '=', node_id), ('is_active', '=', True)], limit=1, order='id desc')
        if not node:
            return {'files': [], 'total': 0, 'page': page, 'total_pages': 0}
        if not self.env['s3.node'].browse(node.id).check_access_for_user(action_name='read', raise_error=False):
            raise AccessError('You do not have read permission on this node.')
        file_model = self.env['s3.stored.file'].sudo()
        domain = [('node_id', '=', node.id), ('is_active', '=', True), ('state', '=', 'stored')]
        if search:
            domain.append(('name', 'ilike', search))
        total = file_model.search_count(domain)
        records = file_model.search(domain, limit=limit, offset=(max(page, 1) - 1) * limit, order='id desc')
        file_data = records.read(['id', 'name', 'size', 'mimetype', 'upload_datetime', 'owner_id', 'state'])
        return {'files': file_data, 'total': total, 'page': page, 'total_pages': (total + limit - 1) // limit}

    def build_download_disposition(self, file_name):
        file_name_text = (file_name or 'download.bin').strip().replace('\\', '_').replace('"', '')
        ascii_name = file_name_text.encode('ascii', 'ignore').decode('ascii').strip() or 'download.bin'
        utf8_name = quote(file_name_text, safe='')
        return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"

    @api.model
    def generate_presigned_url(self, file_id):
        file_model = self.env['s3.stored.file'].sudo()
        file_rec = file_model.search([('id', '=', file_id), ('is_active', '=', True)], limit=1, order='id desc')
        if not file_rec:
            raise UserError('File does not exist.')
        file_record = self.browse(file_rec.id)
        file_record.check_node_access('read')
        config_model = self.env['s3.config']
        config = config_model.get_current_config()
        client = config_model.get_s3_client()
        content_disposition = self.build_download_disposition(file_record.name)
        try:
            url = client.generate_presigned_url('get_object',
                                                Params={'Bucket': config.s3_bucket,
                                                        'Key': file_record.s3_key,
                                                        'ResponseContentDisposition': content_disposition,},
                                                ExpiresIn=config.presigned_url_expiry * 60)
        except (BotoCoreError, ClientError) as error:
            raise UserError(f'Generate download url failed: {error}') from error
        log_model = self.env['s3.operation.log']
        operate_type_model = self.env['s3.operate.type'].sudo()
        download_operate_type = operate_type_model.search([('code', '=', 'download')], limit=1, order='id desc')
        log_model.create_log_line({'operate_type_id': download_operate_type.id if download_operate_type else False, 'file_name': file_record.name, 'file_path': file_record.s3_key, 'operate_result': 'success'})
        return url

    def action_download_file(self):
        action_result = False
        for rec in self:
            if rec.state != 'stored' or not rec.is_active:
                raise UserError('Only stored file can be downloaded.')
            url = rec.generate_presigned_url(rec.id)
            action_result = {'type': 'ir.actions.act_url', 'url': url, 'target': 'self'}
        return action_result

    def action_move_to_recycle_bin(self, delete_reason=''):
        config_model = self.env['s3.config']
        config = config_model.get_current_config()
        client = config_model.get_s3_client()
        recycle_model_sudo = self.env['s3.recycle.entry'].sudo()
        recycle_model = self.env['s3.recycle.entry']
        log_model = self.env['s3.operation.log']
        operate_type_model = self.env['s3.operate.type'].sudo()
        delete_operate_type = operate_type_model.search([('code', '=', 'delete')], limit=1, order='id desc')
        for rec in self:
            if rec.state != 'stored' or not rec.is_active:
                continue
            rec.check_node_access('delete')
            recycle_key = f"{config.prefix_recycle}user_{self.env.uid}/{rec.s3_key}"
            exists_count = recycle_model_sudo.search_count([('file_id', '=', rec.id), ('state', '=', 'active')])
            if exists_count:
                continue
            try:
                client.copy_object(Bucket=config.s3_bucket, CopySource={'Bucket': config.s3_bucket, 'Key': rec.s3_key}, Key=recycle_key)
                client.delete_object(Bucket=config.s3_bucket, Key=rec.s3_key)
            except (BotoCoreError, ClientError) as error:
                log_model.create_log_line({'operate_type_id': delete_operate_type.id if delete_operate_type else False, 'file_name': rec.name, 'file_path': rec.s3_key, 'original_path': rec.s3_key, 'operate_result': 'fail', 'delete_reason': delete_reason, 'error_message': str(error)})
                raise UserError(f'Move file to recycle failed: {error}') from error
            recycle_model.create({'file_id': rec.id, 'original_s3_key': rec.s3_key, 'recycle_s3_key': recycle_key, 'deleted_by_id': self.env.uid, 'delete_reason': delete_reason})
            rec.write({'is_active': False, 'state': 'recycled'})
            log_model.create_log_line({'operate_type_id': delete_operate_type.id if delete_operate_type else False, 'file_name': rec.name, 'file_path': recycle_key, 'original_path': rec.s3_key, 'operate_result': 'success', 'delete_reason': delete_reason})
        return True