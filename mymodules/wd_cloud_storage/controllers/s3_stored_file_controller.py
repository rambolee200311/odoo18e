from botocore.exceptions import BotoCoreError, ClientError
from werkzeug.exceptions import Forbidden, NotFound

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request
import logging
from time import perf_counter
_logger = logging.getLogger(__name__)

class S3StoredFileController(http.Controller):

    @http.route('/wd_cloud_storage/content/<int:file_id>', type='http', auth='user', methods=['GET'], csrf=False)
    def content(self, file_id, download='0', **kwargs):
        #start_time = perf_counter()

        file_model_sudo = request.env['s3.stored.file'].sudo()
        file_sudo = file_model_sudo.search([('id', '=', file_id), ('is_active', '=', True)], limit=1, order='id desc')
        #search_time = perf_counter()

        if not file_sudo:
            raise NotFound()

        file_record = request.env['s3.stored.file'].browse(file_sudo.id)
        try:
            file_record.check_node_access('read')
        except AccessError as error:
            raise Forbidden() from error
        #access_time = perf_counter()

        config_model = request.env['s3.config']
        config = config_model.get_current_config()
        #config_time = perf_counter()

        client = config_model.get_s3_client()
        #client_time = perf_counter()

        inline = download not in ('1', 'true', 'True')

        try:
            s3_object = client.get_object(Bucket=config.s3_bucket, Key=file_record.s3_key)
            #get_object_time = perf_counter()

            file_content = s3_object['Body'].read()
            #read_time = perf_counter()
        except (BotoCoreError, ClientError) as error:
            raise NotFound() from error

        # _logger.info(
        #     '[wd_cloud_content_timing] file_id=%s search=%.1fms access=%.1fms config=%.1fms client=%.1fms get_object=%.1fms read=%.1fms total=%.1fms',
        #     file_id,
        #     (search_time - start_time) * 1000,
        #     (access_time - search_time) * 1000,
        #     (config_time - access_time) * 1000,
        #     (client_time - config_time) * 1000,
        #     (get_object_time - client_time) * 1000,
        #     (read_time - get_object_time) * 1000,
        #     (read_time - start_time) * 1000,
        # )

        mimetype = file_record.mimetype or s3_object.get('ContentType') or 'application/octet-stream'
        disposition = file_record.build_content_disposition(file_record.name, inline=inline)

        return request.make_response(file_content, headers=[
            ('Content-Type', mimetype),
            ('Content-Length', str(len(file_content))),
            ('Content-Disposition', disposition),
            ('Cache-Control', 'no-store'),
        ])
