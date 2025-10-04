from odoo import models, api, fields
import requests
import json
from datetime import datetime, timedelta
from odoo.exceptions import UserError
import logging
import pytz

_logger = logging.getLogger(__name__)


class OutboundOrderStatus(models.Model):
    _inherit = 'world.depot.outbound.order'

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


    # 禾迈-拣货开始
    def action_set_status_to_confirmed(self):
        for order in self:
            if order.project and order.project.name.lower() == 'hoymiles':
                local_time = self.get_local_time('NL', order.confirm_time_server)
                payload = {
                    "thirdPartyWsCode": "WD",
                    "thirdPartyWsName": "WD warehouse",
                    "wsOpOrderNo": order.billno,
                    "reference": order.reference,
                    "operateType": "START_OPERATION",
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
                _source = 'Outbound Order Start Operation'
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
                    return False
            return True

    # 禾迈-拣货完成
    def action_set_status_to_pick_finished(self):
        for order in self:
            if order.project and order.project.name.lower() == 'hoymiles':
                local_time = self.get_local_time('NL', order.picking_PICK.date_done)
                payload = {
                    "thirdPartyWsCode": "WD",
                    "thirdPartyWsName": "WD warehouse",
                    "wsOpOrderNo": order.billno,
                    "reference": order.reference,
                    "operateType": "PICK_FINISHED",
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
                _source = 'Outbound Order Pick Finished'
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
                    return False
            return True

    # 禾迈-出库打包
    def action_set_outbound_pack_sync(self):
        for order in self:
            if order.project and order.project.name.lower() == 'hoymiles':
                local_time = self.get_local_time('NL', order.picking_PICK.date_done)
                payload = {
                    "thirdPartyWsCode": "WD",
                    "thirdPartyWsName": "WD warehouse",
                    "wsOpOrderNo": order.picking_PICK.name if order.picking_PICK else "",
                    "reference": order.reference,
                    "grossWeight": 25,
                    "netWeight": 20,
                    "boxPalletSpec": " 1 Box  80*60*40cm",
                    "packingFinishedTime": local_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "packingMethod": "BOX",
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

                if order.picking_PICK:
                    for line in order.picking_PICK.move_ids:
                        line_data = {
                            "itemNum": line.product_id.barcode if line.product_id else "",
                            "receivedQuantity": line.quantity if line.quantity else 0,
                        }
                        payload['lines'].append(line_data)

                        for move_line in line.move_line_ids:
                            if move_line.lot_id:
                                serial_data = {
                                    "serialNumber": move_line.lot_id.name if move_line.lot_id else "",
                                }
                                payload['serials'].append(serial_data)

                token = order.env['hoymiles.token.utils'].get_oauth_token()

                if not token:
                    raise UserError("Failed to retrieve OAuth token.")

                url = self.env['hoymiles.api.urls'].search([('name', '=', 'outbound-pack-sync')], limit=1)
                if not url or not url.url:
                    raise UserError("API URL configuration is missing.")

                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {token}'
                }
                _source = 'Outbound Pack'
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
                    return False
            return True

    # 禾迈-出库物流信息
    def action_set_logistics_info_sync(self):
        for order in self:
            if order.project and order.project.name.lower() == 'hoymiles':
                local_time = self.get_local_time('NL', order.picking_PICK.date_done)
                payload = {
                    "thirdPartyWsCode": "WD",
                    "thirdPartyWsName": "WD warehouse",
                    "wsOpOrderNo": order.billno if order.billno else "",
                    "reference": order.reference,
                    "logisticsCarrierCode": order.delivery_company.name if order.delivery_company else "",
                    "logisticsCarrierName": order.delivery_company.name if order.delivery_company else "",
                    "trackingNumber": order.delivery_number if order.delivery_number else "",
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

                token = order.env['hoymiles.token.utils'].get_oauth_token()

                if not token:
                    raise UserError("Failed to retrieve OAuth token.")

                url = self.env['hoymiles.api.urls'].search([('name', '=', 'logistics_info_sync')], limit=1)
                if not url or not url.url:
                    raise UserError("API URL configuration is missing.")

                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {token}'
                }
                _source = 'Logistics Info'
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
                    return False
            return True

    # 禾迈 -出库结果
    def action_set_outbound_result_sync(self):
        for order in self:
            if order.project and order.project.name.lower() == 'hoymiles':
                if order.picking_PICK:
                    outbound = self.env['stock.picking'].search(
                        [('origin', '=', order.picking_PICK.name), ('picking_type_code', '=', 'outgoing')], limit=1)
                    local_time = self.get_local_time('NL', outbound.date_done)
                    if outbound:
                        payload = {
                            "thirdPartyWsCode": "WD",
                            "thirdPartyWsName": "WD warehouse",
                            "wsOpOrderNo": outbound.name if outbound else "",
                            "reference": order.reference,
                            "outboundTime": local_time.strftime("%Y-%m-%d %H:%M:%S"),
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

                        for line in outbound.move_ids:
                            line_data = {
                                "itemNum": line.product_id.barcode if line.product_id else "",
                                "shipQuantity": line.quantity if line.quantity else 0,
                                "shipTime": local_time.strftime("%Y-%m-%d %H:%M:%S"),
                            }
                            payload['lines'].append(line_data)
                            '''
                            for move_line in line.move_line_ids:
                                if move_line.lot_id:
                                    serial_data = {
                                        "serialNumber": move_line.lot_id.name if move_line.lot_id else "",
                                    }
                                    payload['serials'].append(serial_data)
                            '''

                        token = order.env['hoymiles.token.utils'].get_oauth_token()

                        if not token:
                            raise UserError("Failed to retrieve OAuth token.")

                        url = self.env['hoymiles.api.urls'].search([('name', '=', 'outbound-result-sync')], limit=1)
                        if not url or not url.url:
                            raise UserError("API URL configuration is missing.")

                        headers = {
                            'Content-Type': 'application/json',
                            'Authorization': f'Bearer {token}'
                        }
                        _source = 'Outbound Result'
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
                            return False
                    return True




