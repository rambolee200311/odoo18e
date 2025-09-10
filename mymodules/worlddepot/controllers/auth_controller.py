import secrets
from datetime import datetime, timedelta
from odoo import http
from odoo.http import request
import json

class AuthController(http.Controller):

    @http.route('/world_depot/api/auth/token', type='json', auth='none', methods=['POST'], csrf=False)
    def generate_token(self, **params):
        data = json.loads(request.httprequest.data)
        api_key = data.get('api_key')
        api_secret = data.get('api_secret')

        if not api_key or not api_secret:
            return {'error': 'Missing API credentials'}

        # Search only by api_key and active status
        api_user = request.env['world.depot.api.user'].sudo().search([
            ('api_key', '=', api_key),
            ('active', '=', True)
        ], limit=1)

        # Verify existence and secret validity
        if not api_user or not api_user.verify_secret(api_secret):
            return {'error': 'Invalid credentials'}

        # Generate secure token (32 random bytes)
        token = secrets.token_urlsafe(32)
        expires = datetime.now() + timedelta(hours=1)

        # Store token
        request.env['world.depot.api.token'].sudo().create({
            'user_id': api_user.user_id.id,
            'token': token,
            'expires': expires
        })

        return {
            'access_token': token,
            'expires_in': 3600,
            'expires_at': expires.strftime('%Y-%m-%d %H:%M:%S')
        }

