import logging
import re

from botocore.exceptions import BotoCoreError, ClientError

from odoo import api, models
from odoo.exceptions import UserError
from odoo.http import Stream

_logger = logging.getLogger(__name__)


class IrAttachmentInherit(models.Model):
    _inherit = 'ir.attachment'

    attachment_s3_uri_pattern = re.compile(r'^s3://(?P<bucket>[^/]+)/(?P<key>.+)$')

    def get_attachment_cloud_config(self):
        config_model = self.env['s3.config'].sudo()
        config = config_model.search([], limit=1, order='id desc')
        return config

    def parse_attachment_s3_uri(self, fname):
        match = self.attachment_s3_uri_pattern.match(fname or '')
        if not match:
            return None
        return {'bucket': match.group('bucket'), 'key': match.group('key')}

    def build_attachment_s3_key(self, checksum):
        config = self.get_attachment_cloud_config()
        if not config:
            raise UserError('Please configure cloud storage first.')
        checksum_value = checksum or 'empty'
        prefix = (config.attachment_prefix or 'odoo-attachments/').strip('/')
        return f"{prefix}/{self.env.cr.dbname}/{checksum_value[:2]}/{checksum_value}"

    @api.model
    def _file_write(self, bin_value, checksum):
        config = self.get_attachment_cloud_config()
        if not config or not config.global_attachment_to_cloud:
            return super()._file_write(bin_value, checksum)
        if not all([config.s3_access_key, config.s3_secret_key, config.s3_region, config.s3_bucket]):
            raise UserError('Cloud config is incomplete for attachment upload.')
        client = self.env['s3.config'].get_s3_client()
        storage_key = self.build_attachment_s3_key(checksum)
        try:
            client.head_object(Bucket=config.s3_bucket, Key=storage_key)
        except ClientError as error:
            error_code = str((error.response or {}).get('Error', {}).get('Code', ''))
            http_status = (error.response or {}).get('ResponseMetadata', {}).get('HTTPStatusCode')
            if error_code not in ('404', 'NoSuchKey', 'NotFound') and http_status != 404:
                raise UserError(f'Attachment cloud check failed: {error}') from error
            try:
                client.put_object(Bucket=config.s3_bucket, Key=storage_key, Body=bin_value)
            except (BotoCoreError, ClientError) as put_error:
                raise UserError(f'Attachment cloud upload failed: {put_error}') from put_error
        except BotoCoreError as error:
            raise UserError(f'Attachment cloud check failed: {error}') from error
        return f"s3://{config.s3_bucket}/{storage_key}"

    @api.model
    def _file_read(self, fname):
        s3_data = self.parse_attachment_s3_uri(fname)
        if not s3_data:
            return super()._file_read(fname)
        config = self.get_attachment_cloud_config()
        if not config:
            _logger.info('Attachment cloud read skipped because cloud config not found for %s', fname)
            return b''
        try:
            client = self.env['s3.config'].get_s3_client()
            response = client.get_object(Bucket=s3_data['bucket'], Key=s3_data['key'])
        except (BotoCoreError, ClientError):
            _logger.info('Attachment cloud read failed for %s', fname, exc_info=True)
            return b''
        return response['Body'].read()

    @api.model
    def _file_delete(self, fname):
        s3_data = self.parse_attachment_s3_uri(fname)
        if not s3_data:
            return super()._file_delete(fname)
        attachment_model = self.env['ir.attachment'].sudo()
        remaining = attachment_model.search_count([('store_fname', '=', fname)])
        if remaining:
            return
        config = self.get_attachment_cloud_config()
        if not config:
            _logger.info('Attachment cloud delete skipped because cloud config not found for %s', fname)
            return
        client = self.env['s3.config'].get_s3_client()
        try:
            client.delete_object(Bucket=s3_data['bucket'], Key=s3_data['key'])
        except ClientError as error:
            error_code = str((error.response or {}).get('Error', {}).get('Code', ''))
            http_status = (error.response or {}).get('ResponseMetadata', {}).get('HTTPStatusCode')
            if error_code not in ('404', 'NoSuchKey', 'NotFound') and http_status != 404:
                _logger.info('Attachment cloud delete failed for %s', fname, exc_info=True)
        except BotoCoreError:
            _logger.info('Attachment cloud delete failed for %s', fname, exc_info=True)

    def _to_http_stream(self):
        self.ensure_one()
        s3_data = self.parse_attachment_s3_uri(self.store_fname) if self.store_fname else None
        if not s3_data:
            return super()._to_http_stream()
        file_data = self._file_read(self.store_fname) or b''
        stream = Stream(type='data', data=file_data, mimetype=self.mimetype, download_name=self.name, etag=self.checksum, public=self.public)
        stream.last_modified = self.write_date
        stream.size = len(file_data)
        return stream