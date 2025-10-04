import logging
import json
from functools import wraps
from datetime import datetime
from odoo.http import request
from odoo import models, fields

_logger = logging.getLogger(__name__)


class APILogs(models.Model):
    _name = 'hoymiles.api.logs'
    _description = 'API Logs'

    request_source = fields.Char(string='Request Source')
    request_time = fields.Datetime(string='Request Time', help='Time when the request was received')
    request_path = fields.Char(string='Request Path', help='API endpoint path')
    request_data = fields.Text(string='Request Data', help='Payload of the API request')
    response_data = fields.Text(string='Response Data', help='Payload of the API response')
    exception_details = fields.Text(string='Exception Details', help='Details of any exception that occurred')
    def api_log_wrapper(func):
        def wrapper(*args, **kwargs):
            try:
                # 尝试执行原始函数
                response = func(*args, **kwargs)
                # 如果成功，创建API日志
                try:
                    request.env['world.depot.api.log'].sudo().create({
                        'name': 'API Call',
                        'request_data': str(kwargs.get('data', {})),
                        'response_data': str(response),
                        'status': 'success'
                    })
                except Exception as e:
                    _logger.error("Failed to create API log: %s", e)
                    # 不要重新抛出，避免影响主响应
                return response
            except Exception as e:
                # 如果主函数失败，记录错误并回滚事务
                _logger.error("API call failed: %s", e)
                try:
                    # 尝试创建错误日志
                    request.env['world.depot.api.log'].sudo().create({
                        'name': 'API Call Error',
                        'request_data': str(kwargs.get('data', {})),
                        'response_data': str(e),
                        'status': 'error'
                    })
                except Exception as log_error:
                    _logger.error("Failed to create error log: %s", log_error)
                # 重新抛出异常以便上层处理
                raise

        return wrapper
