import secrets
from datetime import datetime, timedelta
from odoo import http
from odoo.http import request
import json
from .api_logs import api_logger


class AuthController(http.Controller):

    @http.route([
        '/world_depot/api/auth/token',
        '/world_depot/api/auth/getToken',
    ], type='json', auth='none', methods=['POST'], csrf=False)
    @api_logger
    def generate_token(self, **params):
        is_get_token = request.httprequest.path == "/world_depot/api/auth/getToken"

        try:
            data = json.loads(request.httprequest.data or "{}")
            api_key = data.get("api_key")
            api_secret = data.get("api_secret")

            if not api_key or not api_secret:
                if is_get_token:
                    return {
                        "success": False,
                        "msg": "Missing API credentials",
                        "code": "AUTH_ERROR",
                    }
                return {"error": "Missing API credentials"}

            api_user = request.env["world.depot.api.user"].sudo().search([
                ("api_key", "=", api_key),
                ("active", "=", True),
            ], limit=1)

            if not api_user or not api_user.verify_secret(api_secret):
                if is_get_token:
                    return {
                        "success": False,
                        "msg": "Invalid credentials",
                        "code": "AUTH_ERROR",
                    }
                return {"error": "Invalid credentials"}

            token = secrets.token_urlsafe(32)
            expires = datetime.now() + timedelta(hours=1)

            request.env["world.depot.api.token"].sudo().create({
                "user_id": api_user.user_id.id,
                "token": token,
                "expires": expires,
            })

            token_data = {
                "access_token": token,
                "expires_in": 3600,
                "expires_at": expires.strftime("%Y-%m-%d %H:%M:%S"),
            }

            if is_get_token:
                return {
                    "success": True,
                    "data": token_data,
                    "code": "200",
                }

            return token_data

        except Exception as error:
            if is_get_token:
                return {
                    "success": False,
                    "msg": str(error),
                    "code": "SERVER_ERROR",
                }
            return {"error": str(error)}