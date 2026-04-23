from datetime import timedelta

try:
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:
    BotoCoreError = Exception
    ClientError = Exception

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class S3RecycleEntry(models.Model):
    _name = 's3.recycle.entry'
    _description = 'S3 Recycle Entry'
    _order = 'id desc'

    file_id = fields.Many2one('s3.stored.file', string='File', required=True, ondelete='cascade', index=True)
    original_s3_key = fields.Char(string='Original S3 Key', required=True, index=True)
    recycle_s3_key = fields.Char(string='Recycle S3 Key', required=True, index=True)
    deleted_by_id = fields.Many2one('res.users', string='Deleted By', required=True, index=True)
    deletion_datetime = fields.Datetime(string='Deletion Datetime', default=fields.Datetime.now, index=True)
    expiry_datetime = fields.Datetime(string='Expiry Datetime', compute='_compute_expiry_datetime', store=True, index=True)
    remaining_days = fields.Integer(string='Remaining Days', compute='_compute_remaining_days', store=False)
    restore_datetime = fields.Datetime(string='Restore Datetime')
    purged_datetime = fields.Datetime(string='Purged Datetime')
    state = fields.Selection([('active', 'Active'), ('restored', 'Restored'), ('purged', 'Purged')], string='State', default='active', required=True, index=True)
    delete_reason = fields.Char(string='Delete Reason')
    clean_reason = fields.Char(string='Clean Reason')
    owner_id = fields.Many2one('res.users', string='File Owner', related='file_id.owner_id', store=True, index=True)

    @api.depends('deletion_datetime')
    def _compute_expiry_datetime(self):
        config_model = self.env['s3.config']
        retention_days = config_model.get_recycle_retention_days()
        for rec in self:
            rec.expiry_datetime = rec.deletion_datetime + timedelta(days=retention_days) if rec.deletion_datetime else False
#回收站动态算剩余天数
    @api.depends('expiry_datetime')
    def _compute_remaining_days(self):
        now_dt = fields.Datetime.now()
        for rec in self:
            if not rec.expiry_datetime:
                rec.remaining_days = 0
            else:
                delta = rec.expiry_datetime - now_dt
                rec.remaining_days = max(delta.days, 0)

    def check_recycle_access(self, action_name='read', raise_error=True):
        allowed = True
        is_admin = self.env.user.has_group('wd_cloud_storage.group_wd_cloud_storage_admin')
        for rec in self:
            rec_allowed = is_admin or rec.deleted_by_id.id == self.env.uid
            if not rec_allowed:
                allowed = False
                if raise_error:
                    raise AccessError('You do not have permission for this recycle entry.')
        return allowed

    def action_restore(self):
        config_model = self.env['s3.config']
        config = config_model.get_current_config()
        client = config_model.get_s3_client()
        log_model = self.env['s3.operation.log']
        operate_type_model = self.env['s3.operate.type'].sudo()
        restore_operate_type = operate_type_model.search([('code', '=', 'restore')], limit=1, order='id desc')
        for rec in self:
            if rec.state != 'active':
                continue
            rec.check_recycle_access('restore')
            if not rec.file_id:
                continue
            rec.file_id.node_id.check_access_for_user(action_name='write')
            try:
                client.copy_object(Bucket=config.s3_bucket, CopySource={'Bucket': config.s3_bucket, 'Key': rec.recycle_s3_key}, Key=rec.original_s3_key)
                client.delete_object(Bucket=config.s3_bucket, Key=rec.recycle_s3_key)
            except (BotoCoreError, ClientError) as error:
                log_model.create_log_line({'operate_type_id': restore_operate_type.id if restore_operate_type else False, 'file_name': rec.file_id.name, 'file_path': rec.recycle_s3_key, 'original_path': rec.original_s3_key, 'operate_result': 'fail', 'error_message': str(error)})
                raise UserError(f'Restore file failed: {error}') from error
            rec.file_id.write({'is_active': True, 'state': 'stored'})
            rec.write({'state': 'restored', 'restore_datetime': fields.Datetime.now()})
            log_model.create_log_line({'operate_type_id': restore_operate_type.id if restore_operate_type else False, 'file_name': rec.file_id.name, 'file_path': rec.original_s3_key, 'original_path': rec.recycle_s3_key, 'operate_result': 'success'})
        return True

    def action_purge(self, clean_reason='manual'):
        config_model = self.env['s3.config']
        config = config_model.get_current_config()
        client = config_model.get_s3_client()
        log_model = self.env['s3.operation.log']
        operate_type_model = self.env['s3.operate.type'].sudo()
        purge_operate_type = operate_type_model.search([('code', '=', 'purge')], limit=1, order='id desc')
        for rec in self:
            if rec.state == 'purged':
                continue
            rec.check_recycle_access('purge')
            try:
                client.delete_object(Bucket=config.s3_bucket, Key=rec.recycle_s3_key)
            except ClientError as error:
                error_code = str((error.response or {}).get('Error', {}).get('Code', ''))
                http_status = (error.response or {}).get('ResponseMetadata', {}).get('HTTPStatusCode')
                if error_code not in ('404', 'NoSuchKey', 'NotFound') and http_status != 404:
                    log_model.create_log_line({'operate_type_id': purge_operate_type.id if purge_operate_type else False, 'file_name': rec.file_id.name if rec.file_id else False, 'file_path': rec.recycle_s3_key, 'operate_result': 'fail', 'clean_reason': clean_reason, 'error_message': str(error)})
                    raise UserError(f'Purge file failed: {error}') from error
            except BotoCoreError as error:
                log_model.create_log_line({'operate_type_id': purge_operate_type.id if purge_operate_type else False, 'file_name': rec.file_id.name if rec.file_id else False, 'file_path': rec.recycle_s3_key, 'operate_result': 'fail', 'clean_reason': clean_reason, 'error_message': str(error)})
                raise UserError(f'Purge file failed: {error}') from error
            rec.write({'state': 'purged', 'purged_datetime': fields.Datetime.now(), 'clean_reason': clean_reason})
            log_model.create_log_line({'operate_type_id': purge_operate_type.id if purge_operate_type else False, 'file_name': rec.file_id.name if rec.file_id else False, 'file_path': rec.recycle_s3_key, 'operate_result': 'success', 'clean_reason': clean_reason})
        return True

    @api.model
    def get_my_recycle_entries(self, page=1, limit=20, search=None):
        recycle_model = self.env['s3.recycle.entry'].sudo()
        is_admin = self.env.user.has_group('wd_cloud_storage.group_wd_cloud_storage_admin')
        domain = [('state', '=', 'active')]
        if not is_admin:
            domain.append(('deleted_by_id', '=', self.env.uid))
        if search:
            domain.append(('file_id.name', 'ilike', search))
        total = recycle_model.search_count(domain)
        records = recycle_model.search(domain, limit=limit, offset=(max(page, 1) - 1) * limit, order='id desc')
        data = records.read(['id', 'file_id', 'original_s3_key', 'recycle_s3_key', 'deleted_by_id', 'deletion_datetime', 'expiry_datetime', 'state'])
        return {'entries': data, 'total': total, 'page': page, 'total_pages': (total + limit - 1) // limit}

    @api.model
    def cron_purge_expired_entries(self):
        recycle_model = self.env['s3.recycle.entry'].sudo()
        expired_entries = recycle_model.search([('state', '=', 'active'), ('expiry_datetime', '<', fields.Datetime.now())], order='id desc')
        expired_ids = expired_entries.ids
        for rec in self.browse(expired_ids):
            rec.action_purge(clean_reason='auto_expired')
        return True