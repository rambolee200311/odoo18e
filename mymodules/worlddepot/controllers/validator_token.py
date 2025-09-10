# controllers/tools.py
import json
import logging
from odoo import http, fields
from odoo.http import request
from functools import wraps

_logger = logging.getLogger(__name__)


def validate_token(func):
    """Decorator to validate API access tokens"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        # Get token from headers
        token = request.httprequest.headers.get('Authorization')

        if not token:
            _logger.warning("API request missing authentication token")
            return http.Response(
                json.dumps({'error': 'Missing authentication token'}),
                status=401,
                mimetype='application/json'
            )

        # Validate token
        token_rec = request.env['world.depot.api.token'].sudo().search([
            ('token', '=', token)
        ], limit=1)

        if not token_rec:
            _logger.warning("Invalid API token: %s", token)
            return http.Response(
                json.dumps({'error': 'Invalid token'}),
                status=401,
                mimetype='application/json'
            )

        if token_rec.expires < fields.Datetime.now():
            token_rec.unlink()
            _logger.info("Expired token deleted: %s", token)
            return http.Response(
                json.dumps({'error': 'Token expired'}),
                status=401,
                mimetype='application/json'
            )

        # Update environment with authenticated user
        request.update_env(user=token_rec.user_id.id)

        # Proceed to the endpoint function
        return func(*args, **kwargs)

    return wrapper
