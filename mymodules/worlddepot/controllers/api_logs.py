import logging
import json
from functools import wraps
from datetime import datetime
from odoo.http import request
from odoo import models, fields, api, _

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
    status = fields.Selection(
        [('success', 'Success'), ('error', 'Error')],
        string='Status',
        help='Indicates whether the API call was successful or not'
    )

''''
def api_logger(func):
    """Decorator to log API requests, responses, and exceptions using independent transactions."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        # Capture request details at the start
        request_data = request.httprequest.data.decode('utf-8') if request.httprequest.data else ''
        request_source = request.httprequest.remote_addr
        request_time = fields.Datetime.now()
        request_path = request.httprequest.path

        # Execute the endpoint function
        try:
            response = func(*args, **kwargs)
            status = 'success'
            response_str = json.dumps(response) if response else ''
        except Exception as e:
            # Rollback main transaction before handling error
            request.env.cr.rollback()
            status = 'error'
            response_str = ''
            exception_details = str(e)
            response = {
                'error': 'An unexpected error occurred. Please contact support.',
                'details': exception_details
            }
        finally:
            # Always log using a separate transaction
            try:
                # Create log record using a new cursor/environment
                with api.Environment.manage():
                    with request.registry.cursor() as cr:
                        env = api.Environment(cr, request.env.uid, request.env.context)
                        log_vals = {
                            'request_source': request_source,
                            'request_time': request_time,
                            'request_path': request_path,
                            'request_data': request_data,
                            'status': status,
                        }

                        if status == 'success':
                            log_vals['response_data'] = response_str
                        else:
                            log_vals['exception_details'] = exception_details

                        env['world.depot.api.log'].sudo().create(log_vals)
                        cr.commit()
            except Exception as log_exc:
                # If logging fails, fallback to server logs
                _logger.error("API LOG FAILED: %s - %s", request_path, str(log_exc))
                _logger.debug("Request details: %s", {
                    'source': request_source,
                    'path': request_path,
                    'data': request_data
                })

        return response

    return wrapper

'''


def api_logger(func):
    """Decorator to log API requests, responses, and exceptions using independent transactions."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        # Capture request details at the start
        request_data = request.httprequest.data.decode('utf-8') if request.httprequest.data else ''
        request_source = request.httprequest.remote_addr
        request_time = fields.Datetime.now()
        request_path = request.httprequest.path

        # Execute the endpoint function
        try:
            response = func(*args, **kwargs)
            status = 'success'
            response_str = json.dumps(response) if response else ''
            exception_details = None
        except Exception as e:
            # Rollback main transaction before handling error
            request.env.cr.rollback()
            status = 'error'
            response_str = ''
            exception_details = str(e)
            response = {
                'error': 'An unexpected error occurred. Please contact support.',
                'details': exception_details
            }

        # Always log using a separate transaction
        try:
            # Create a new database connection and environment for logging
            db_name = request.env.cr.dbname
            registry = request.registry
            with registry.cursor() as cr:
                # Create a new environment with the new cursor
                env = api.Environment(cr, request.env.uid, request.env.context)

                log_vals = {
                    'request_source': request_source,
                    'request_time': request_time,
                    'request_path': request_path,
                    'request_data': request_data,
                    'status': status,
                }

                if status == 'success':
                    log_vals['response_data'] = response_str
                else:
                    log_vals['exception_details'] = exception_details

                env['world.depot.api.log'].sudo().create(log_vals)
                cr.commit()
        except Exception as log_exc:
            # If logging fails, fallback to server logs
            _logger.error("API LOG FAILED: %s - %s", request_path, str(log_exc))
            _logger.debug("Request details: %s", {
                'source': request_source,
                'path': request_path,
                'data': request_data
            })

        return response

    return wrapper