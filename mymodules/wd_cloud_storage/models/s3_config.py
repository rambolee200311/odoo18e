import mimetypes

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:
    boto3 = None
    BotoCoreError = Exception
    ClientError = Exception

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class S3Config(models.Model):
    _name = 's3.config'
    _description = 'S3 Config'
    _order = 'id desc'

    name = fields.Char(string='Name', required=True, default='S3 Storage Config', copy=False)
    s3_access_key = fields.Char(string='S3 Access Key', required=True, copy=False)
    s3_secret_key = fields.Char(string='S3 Secret Key', required=True, copy=False, groups='base.group_system')
    s3_region = fields.Char(string='S3 Region', required=True, default='eu-central-1')
    s3_bucket = fields.Char(string='S3 Bucket', required=True, index=True)
    presigned_url_expiry = fields.Integer(string='Presigned Url Expiry Minutes', required=True, default=10)
    prefix_private = fields.Char(string='Private Prefix', required=True, default='private/')
    prefix_public = fields.Char(string='Public Prefix', required=True, default='public/')
    prefix_temp = fields.Char(string='Temp Prefix', required=True, default='temp/')
    prefix_recycle = fields.Char(string='Recycle Prefix', required=True, default='recycle/')
    max_file_size_mb = fields.Integer(string='Max File Size Mb', required=True, default=50)
    allowed_file_types = fields.Char(string='Allowed File Types')
    log_retention_days = fields.Integer(string='Log Retention Days', required=True, default=365)
    global_attachment_to_cloud = fields.Boolean(string='Store All Attachments In Cloud', default=False)
    attachment_prefix = fields.Char(string='Attachment Prefix', required=True, default='odoo-attachments/')
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company, index=True, readonly=True)

    def normalize_prefix_text(self, prefix_text, default_prefix):
        value_text = (prefix_text or default_prefix or '').strip()
        if not value_text:
            raise ValidationError('Prefix cannot be empty.')
        return value_text if value_text.endswith('/') else f"{value_text}/"

    def normalize_prefix_values(self, vals):
        if 'prefix_private' in vals:
            vals['prefix_private'] = self.normalize_prefix_text(vals.get('prefix_private'), 'private/')
        if 'prefix_public' in vals:
            vals['prefix_public'] = self.normalize_prefix_text(vals.get('prefix_public'), 'public/')
        if 'prefix_temp' in vals:
            vals['prefix_temp'] = self.normalize_prefix_text(vals.get('prefix_temp'), 'temp/')
        if 'prefix_recycle' in vals:
            vals['prefix_recycle'] = self.normalize_prefix_text(vals.get('prefix_recycle'), 'recycle/')
        if 'attachment_prefix' in vals:
            vals['attachment_prefix'] = self.normalize_prefix_text(vals.get('attachment_prefix'), 'odoo-attachments/')
        return vals

    def validate_values(self, vals):
        file_size = vals.get('max_file_size_mb')
        if file_size is not None and file_size <= 0:
            raise ValidationError('Max file size must be greater than 0.')
        expiry = vals.get('presigned_url_expiry')
        if expiry is not None and (expiry < 5 or expiry > 30):
            raise ValidationError('Presigned Url expiry must be between 5 and 30 minutes.')

    @api.model_create_multi
    def create(self, vals_list):
        config_model = self.env['s3.config'].sudo()
        if len(vals_list) != 1:
            raise ValidationError('Only one S3 config can be created each time.')
        if config_model.search_count([]):
            raise ValidationError('Only one S3 config is allowed.')
        for vals in vals_list:
            self.validate_values(vals)
            self.normalize_prefix_values(vals)
        records = super().create(vals_list)
        self.env['s3.node'].ensure_base_nodes()
        return records

    def write(self, vals):
        self.validate_values(vals)
        self.normalize_prefix_values(vals)
        for rec in self:
            if vals.get('company_id') and vals.get('company_id') != rec.company_id.id:
                raise ValidationError('Company cannot be changed.')
        result = super().write(vals)
        if any(key in vals for key in ('prefix_public', 'prefix_temp', 'prefix_recycle')):
            self.env['s3.node'].ensure_base_nodes()
        return result

    @api.model
    def get_current_config(self):
        config_model = self.env['s3.config'].sudo()
        config = config_model.search([], limit=1, order='id desc')
        if not config:
            raise UserError('Please configure cloud storage first.')
        return self.browse(config.id)
   # 回收站天数
    @api.model
    def get_recycle_retention_days(self):
        return 90

    @api.model
    def get_s3_client(self):
        config = self.get_current_config()
        if boto3 is None:
            raise UserError('Please install boto3 and botocore first.')
        if not all([config.s3_access_key, config.s3_secret_key, config.s3_region, config.s3_bucket]):
            raise UserError('S3 access key, secret key, region and bucket are required.')
        return boto3.client('s3', aws_access_key_id=config.s3_access_key, aws_secret_access_key=config.s3_secret_key, region_name=config.s3_region)

    @api.model
    def check_upload_rule(self, file_size, file_name, mimetype=''):
        config = self.get_current_config()
        size_limit = config.max_file_size_mb * 1024 * 1024
        if file_size > size_limit:
            raise UserError(f'File exceeds size limit {config.max_file_size_mb}MB.')
        if not config.allowed_file_types:
            return True
        allowed_values = [item.strip().lower() for item in config.allowed_file_types.split(',') if item.strip()]
        if not allowed_values:
            return True
        file_name_lower = (file_name or '').lower()
        mime_type = (mimetype or mimetypes.guess_type(file_name_lower)[0] or '').lower()
        for allowed in allowed_values:
            if allowed.endswith('/*') and mime_type.startswith(allowed[:-1]):
                return True
            if allowed.startswith('.') and file_name_lower.endswith(allowed):
                return True
            if allowed == mime_type:
                return True
        raise UserError('File type is not allowed by system config.')
#一键初始化部门文件夹和管理员文件夹
    def action_init_public_folders(self):
        self.env['s3.node'].action_init_public_folders()
        return True

    def action_test_connection(self):
        for rec in self:
            if boto3 is None:
                raise UserError('Please install boto3 and botocore first.')
            if not all([rec.s3_access_key, rec.s3_secret_key, rec.s3_region, rec.s3_bucket]):
                raise UserError('S3 access key, secret key, region and bucket are required.')
            client = boto3.client('s3', aws_access_key_id=rec.s3_access_key, aws_secret_access_key=rec.s3_secret_key, region_name=rec.s3_region)
            try:
                client.head_bucket(Bucket=rec.s3_bucket)
            except (BotoCoreError, ClientError) as error:
                raise UserError(f'S3 connection failed: {error}') from error
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': 'Success',
                'message': 'S3 connection is available.',
                'sticky': False,
            },
        }