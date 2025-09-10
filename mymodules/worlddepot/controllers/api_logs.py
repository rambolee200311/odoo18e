import logging
import json
from functools import wraps
from datetime import datetime
from odoo.http import request
from odoo import models, fields

_logger = logging.getLogger(__name__)


class APILog(models.Model):
    _name = 'world.depot.api.log'
    _description = 'API Log'

    request_source = fields.Char(string='Request Source', help='IP address of the request source')
    request_time = fields.Datetime(string='Request Time', help='Time when the request was received')
    request_path = fields.Char(string='Request Path', help='API endpoint path')
    request_data = fields.Text(string='Request Data', help='Payload of the API request')
    response_data = fields.Text(string='Response Data', help='Payload of the API response')
    exception_details = fields.Text(string='Exception Details', help='Details of any exception that occurred')


def api_logger(func):
    """Decorator to log API requests, responses, and exceptions."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            # Log the incoming request details
            request_data = request.httprequest.data.decode('utf-8')
            request_source = request.httprequest.remote_addr
            request_time = fields.Datetime.now()
            request_path = request.httprequest.path

            # Execute the endpoint function
            response = func(*args, **kwargs)

            # Save log to the database
            request.env['world.depot.api.log'].sudo().create({
                'request_source': request_source,
                'request_time': request_time,
                'request_path': request_path,
                'request_data': request_data,
                'response_data': json.dumps(response),
            })

            return response
        except Exception as e:
            # Save exception log to the database
            request.env['world.depot.api.log'].sudo().create({
                'request_source': request.httprequest.remote_addr,
                'request_time': fields.Datetime.now(),
                'request_path': request.httprequest.path,
                'request_data': request.httprequest.data.decode('utf-8'),
                'exception_details': str(e),
            })
            return {
                'error': 'An unexpected error occurred. Please contact support.',
                'details': str(e)
            }

    return wrapper

def wrapper(func):
    def wrapped(*args, **kwargs):
        try:
            # Your main logic here
            result = func(*args, **kwargs)

            # Log the API call
            try:
                request.env.cr.rollback()  # Rollback any failed transaction
                request.env['world.depot.api.log'].sudo().create({
                    'name': 'API Call',
                    'details': 'Log details here',
                })
            except Exception as log_error:
                request.env.cr.rollback()  # Ensure rollback if logging fails
                _logger.error("Failed to log API call: %s", str(log_error))

            return result
        except Exception as e:
            request.env.cr.rollback()  # Rollback the transaction
            _logger.error("Error in API call: %s", str(e))
            return {'success': False, 'error': str(e)}
    return wrapped
