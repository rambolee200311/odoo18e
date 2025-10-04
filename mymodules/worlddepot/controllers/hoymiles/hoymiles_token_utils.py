from odoo import models, api, fields
import requests
import json
from datetime import datetime, timedelta
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class TokenUtils(models.Model):
    _name = 'hoymiles.token.utils'
    _description = 'Hoymiles OAuth Token Utility Model'

    # Optional: Fields to store token details if needed for logging or tracking
    token_url = fields.Char(string='Token Endpoint')
    last_token = fields.Char(string='Last Access Token')
    token_expiry = fields.Datetime(string='Token Expiry Time')
    client_id = fields.Char(string='Client ID')
    client_secret = fields.Char(string='Client Secret')  # In production, store this securely in config parameters

    @api.model
    def get_oauth_token(self):
        """
        Public method to fetch OAuth access token using client credentials grant.
        Returns: access_token (str) or False on failure.
        """
        # Retrieve credentials (consider storing secrets in ir.config_parameter for security)
        url = self.env['hoymiles.api.urls'].search([('name', '=', 'access_token')], limit=1)
        if not url:
            raise UserError("Token URL configuration is missing.")
        if not url.url or not url.parameters_form:
            raise UserError("Token URL or parameters are not properly configured.")

        client_id = 'thirdPartyClient'
        grant_type = 'client_credentials'
        client_secret = url.parameters_form  # Assuming client_secret is stored here for this example
        token_url = url.url

        payload = {
            'client_id': client_id,
            'grant_type': grant_type,
            'client_secret': client_secret
        }
        '''
        headers = {
            'Content-Type': 'application/json',
        }
        '''
        try:
            response = requests.post(
                token_url,
                data=payload,
                timeout=10
            )

            if response.status_code == 200:
                token_data = response.json()
                access_token = token_data.get('access_token')
                expires_in = token_data.get('expires_in', 319)
                # Calculate expiry time (optional: store for caching)
                self.last_token = access_token
                self.token_expiry = datetime.now() + timedelta(seconds=expires_in)
                # write api log
                self.env['hoymiles.api.logs'].sudo().create({
                    'request_source': 'Token Fetch',
                    'request_time': datetime.now(),
                    'request_path': token_url,
                    'request_data': json.dumps(payload),
                    'response_data': response.text
                })
                return access_token
            else:
                _logger.error("Token fetch failed: HTTP %s - %s", response.status_code, response.text)
                # write api log
                self.env['hoymiles.api.logs'].sudo().create({
                    'request_source': 'Token Fetch',
                    'request_time': datetime.now(),
                    'request_path': token_url,
                    'request_data': json.dumps(payload),
                    'response_data': response.text,
                    'exception_details': f"HTTP {response.status_code}"
                })
                return False

        except requests.exceptions.RequestException as e:

            _logger.error("Network error during token fetch: %s", str(e))
            # write api log
            self.env['hoymiles.api.logs'].sudo().create({
                'request_source': 'Token Fetch',
                'request_time': datetime.now(),
                'request_path': token_url,
                'request_data': json.dumps(payload),
                'response_data': False,
                'exception_details': str(e)
            })
            return False
        except json.JSONDecodeError as e:
            _logger.error("JSON decode error in token response: %s", str(e))
            # write api log
            self.env['hoymiles.api.logs'].sudo().create({
                'request_source': 'Token Fetch',
                'request_time': datetime.now(),
                'request_path': token_url,
                'request_data': json.dumps(payload),
                'response_data': False,
                'exception_details': str(e)
            })
            return False
