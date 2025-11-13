from odoo import models, api, fields
import requests
import json
from datetime import datetime, timedelta
from odoo.exceptions import UserError
import logging
import pytz

_logger = logging.getLogger(__name__)


class InboundOrderStatus(models.Model):
    _inherit = 'world.depot.inbound.order'

    def get_local_time(self, country_code, utc_time):
        """
        Convert UTC time to local time for a specified country/region.

        Args:
            country_code (str): ISO country code (e.g., 'NL', 'CN', 'US')
            utc_time (datetime): UTC time (can be either timezone-aware or naive datetime)

        Returns:
            datetime: Local time as timezone-aware datetime object

        Raises:
            ValueError: If country_code is invalid or timezone conversion fails
        """
        if not country_code:
            country_code = 'NL'  # Default to Netherlands

        # Handle utc_time parameter
        if not utc_time:
            # Use current UTC time (timezone-aware)
            utc_time = datetime.now(pytz.UTC)
        elif utc_time.tzinfo is None:
            # If naive datetime, assume it's UTC time
            utc_time = pytz.UTC.localize(utc_time)

        # Normalize country code to uppercase
        normalized_country_code = country_code.upper() if country_code else 'NL'

        # Get country timezones
        country_timezones = pytz.country_timezones.get(normalized_country_code, [])

        if not country_timezones:
            # Log warning and fallback to UTC
            _logger.warning("No timezone found for country code: %s. Using UTC as fallback.", country_code)
            return utc_time.astimezone(pytz.UTC)

        # Select the first timezone for the country
        # Note: For countries with multiple timezones, more sophisticated logic might be needed
        local_tz = pytz.timezone(country_timezones[0])

        # Convert timezone
        local_time = utc_time.astimezone(local_tz)
        return local_time

    # 禾迈-入库状态
    set_status_to_confirmed=fields.Boolean(string="Set Status to Confirmed", default=False)
    set_status_to_confirmed_time=fields.Datetime(string="Status to Confirmed Time", readonly=True)
    status_to_confirmed_error_msg=fields.Text(string="Status to Confirmed Error Msg", readonly=True)
    def action_set_status_to_confirmed(self):
        for order in self:
            if order.project and order.project.name.lower() == 'hoymiles':
                local_time = self.get_local_time('NL', order.confirm_time_server)
                payload = {
                    "thirdPartyWsCode": "WD",
                    "thirdPartyWsName": "WD warehouse",
                    "wsOpOrderNo": order.billno,
                    "reference": order.reference,
                    "operateType": "INBOUND_CONFIRM",
                    "operationTime": local_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "attribute1": "",
                    "attribute2": "",
                    "attribute3": "",
                    "attribute4": "",
                    "attribute5": "",
                    "attribute6": "",
                    "attribute7": "",
                    "attribute8": "",
                    "attribute9": "",
                    "attribute10": ""
                }

                token = order.env['hoymiles.token.utils'].get_oauth_token()

                if not token:
                    raise UserError("Failed to retrieve OAuth token.")

                url = self.env['hoymiles.api.urls'].search([('name', '=', 'doc-status-sync')], limit=1)
                if not url or not url.url:
                    raise UserError("API URL configuration is missing.")

                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {token}'
                }
                _source = 'Inbound Order Confirmd'
                try:
                    response = requests.post(
                        url.url,
                        headers=headers,
                        data=json.dumps(payload),
                        timeout=10
                    )

                    if response.status_code == 200:
                        response_data = response.json()
                        failed = response_data.get('failed')

                        # write api log
                        self.env['hoymiles.api.logs'].sudo().create({
                            'request_source': _source,
                            'request_time': datetime.now(),
                            'request_path': url.url,
                            'request_data': json.dumps(payload),
                            'response_data': response.text
                        })
                        if not failed:
                            order.write({
                                'set_status_to_confirmed': True,    
                                'set_status_to_confirmed_time': datetime.now(),
                                'status_to_confirmed_error_msg': False,
                            })
                        else:
                            if not order.set_status_to_confirmed:
                                order.write({
                                    'set_status_to_confirmed': False,    
                                    'set_status_to_confirmed_time': datetime.now(),
                                    'status_to_confirmed_error_msg': response.text
                            })   
                        return failed
                    else:
                        _logger.error("Token fetch failed: HTTP %s - %s", response.status_code, response.text)
                        # write api log
                        self.env['hoymiles.api.logs'].sudo().create({
                            'request_source': _source,
                            'request_time': datetime.now(),
                            'request_path': url.url,
                            'request_data': json.dumps(payload),
                            'response_data': response.text,
                            'exception_details': f"HTTP {response.status_code}"
                        })
                        if not order.set_status_to_confirmed:
                                order.write({
                                    'set_status_to_confirmed': False,    
                                    'set_status_to_confirmed_time': datetime.now(),
                                    'status_to_confirmed_error_msg': response.text
                            })   
                        return False

                except requests.exceptions.RequestException as e:

                    _logger.error("Network error during token fetch: %s", str(e))
                    # write api log
                    self.env['hoymiles.api.logs'].sudo().create({
                        'request_source': _source,
                        'request_time': datetime.now(),
                        'request_path': url.url,
                        'request_data': json.dumps(payload),
                        'response_data': False,
                        'exception_details': str(e)
                    })
                    if not order.set_status_to_confirmed:
                                order.write({
                                    'set_status_to_confirmed': False,    
                                    'set_status_to_confirmed_time': datetime.now(),
                                    'status_to_confirmed_error_msg': str(e)
                            })   
                    return False
                except json.JSONDecodeError as e:
                    _logger.error("JSON decode error in token response: %s", str(e))
                    # write api log
                    self.env['hoymiles.api.logs'].sudo().create({
                        'request_source': _source,
                        'request_time': datetime.now(),
                        'request_path': url.url,
                        'request_data': json.dumps(payload),
                        'response_data': False,
                        'exception_details': str(e)
                    })
                    if not order.set_status_to_confirmed:
                                order.write({
                                    'set_status_to_confirmed': False,    
                                    'set_status_to_confirmed_time': datetime.now(),
                                    'status_to_confirmed_error_msg': str(e)
                            })   
                    return False
            return True

    # 禾迈-入库结果
    set_inbound_result_sync=fields.Boolean(string="Set Inbound Result Sync", default=False)
    set_inbound_result_sync_time=fields.Datetime(string="Inbound Result Sync Time", readonly=True)
    inbound_result_sync_error_msg=fields.Text(string="Inbound Result Sync Error Msg", readonly=True)
    def action_set_inbound_result_sync(self):
        for order in self:
            if order.project and order.project.name.lower() == 'hoymiles':

                country_code = 'NL'
                local_time = self.get_local_time(country_code, order.stock_picking_id.date_done)
                payload = {
                    "thirdPartyWsCode": "WD",
                    "thirdPartyWsName": "WD warehouse",
                    "wsOpOrderNo": order.stock_picking_id.name if order.stock_picking_id else "",
                    "reference": order.reference,
                    "receivedTime": local_time.strftime(
                        "%Y-%m-%d %H:%M:%S") if local_time else "",
                    "attribute1": "",
                    "attribute2": "",
                    "attribute3": "",
                    "attribute4": "",
                    "attribute5": "",
                    "attribute6": "",
                    "attribute7": "",
                    "attribute8": "",
                    "attribute9": "",
                    "attribute10": "",
                    "lines": [],
                    "serials": []
                }

                if order.stock_picking_id:
                    for line in order.stock_picking_id.move_ids:
                        line_data = {
                            "itemNum": line.product_id.barcode if line.product_id else "",
                            "receivedQuantity": line.quantity if line.quantity else 0,
                        }
                        payload['lines'].append(line_data)
                        # 备货不回传，服务回传
                        if order.type == 'service':
                            for move_line in line.move_line_ids:
                                if move_line.lot_id:
                                    serial_data = {
                                        "serialNumber": move_line.lot_id.name if move_line.lot_id else "",
                                    }
                                    payload['serials'].append(serial_data)

                token = order.env['hoymiles.token.utils'].get_oauth_token()

                if not token:
                    raise UserError("Failed to retrieve OAuth token.")

                url = self.env['hoymiles.api.urls'].search([('name', '=', 'inbound_result_sync')], limit=1)
                if not url or not url.url:
                    raise UserError("API URL configuration is missing.")

                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {token}'
                }
                _source = 'Inbound Result'
                try:
                    response = requests.post(
                        url.url,
                        headers=headers,
                        data=json.dumps(payload),
                        timeout=10
                    )

                    if response.status_code == 200:
                        response_data = response.json()
                        failed = response_data.get('failed')

                        # write api log
                        self.env['hoymiles.api.logs'].sudo().create({
                            'request_source': _source,
                            'request_time': datetime.now(),
                            'request_path': url.url,
                            'request_data': json.dumps(payload),
                            'response_data': response.text
                        })
                        if not failed:
                            order.write({
                                'set_inbound_result_sync': True,    
                                'set_inbound_result_sync_time': datetime.now(),
                                'inbound_result_sync_error_msg': False,
                            })
                        else:
                            if not order.set_inbound_result_sync:
                                order.write({
                                    'set_inbound_result_sync': False,    
                                    'set_inbound_result_sync_time': datetime.now(),
                                    'inbound_result_sync_error_msg': response.text
                            })
                        return failed
                    else:
                        _logger.error("Token fetch failed: HTTP %s - %s", response.status_code, response.text)
                        # write api log
                        self.env['hoymiles.api.logs'].sudo().create({
                            'request_source': _source,
                            'request_time': datetime.now(),
                            'request_path': url.url,
                            'request_data': json.dumps(payload),
                            'response_data': response.text,
                            'exception_details': f"HTTP {response.status_code}"
                        })
                        return False

                except requests.exceptions.RequestException as e:

                    _logger.error("Network error during token fetch: %s", str(e))
                    # write api log
                    self.env['hoymiles.api.logs'].sudo().create({
                        'request_source': _source,
                        'request_time': datetime.now(),
                        'request_path': url.url,
                        'request_data': json.dumps(payload),
                        'response_data': False,
                        'exception_details': str(e)
                    })
                    if not order.set_inbound_result_sync:
                                order.write({
                                    'set_inbound_result_sync': False,    
                                    'set_inbound_result_sync_time': datetime.now(),
                                    'inbound_result_sync_error_msg': str(e)
                            })
                    return False
                except json.JSONDecodeError as e:
                    _logger.error("JSON decode error in token response: %s", str(e))
                    # write api log
                    self.env['hoymiles.api.logs'].sudo().create({
                        'request_source': _source,
                        'request_time': datetime.now(),
                        'request_path': url.url,
                        'request_data': json.dumps(payload),
                        'response_data': False,
                        'exception_details': str(e)
                    })
                    if not order.set_inbound_result_sync:
                                order.write({
                                    'set_inbound_result_sync': False,    
                                    'set_inbound_result_sync_time': datetime.now(),
                                    'inbound_result_sync_error_msg': str(e)
                            })
                    return False
            return True
