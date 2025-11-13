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

    def _ensure_naive_datetime_or_false(self, dt):
        """Return a naive UTC datetime or False.

        Odoo datetime fields expect naive datetimes (no tzinfo). If `dt` is timezone-aware,
        convert it to UTC and strip tzinfo. If dt is None or False, return False so callers
        can write False to clear the field.
        """
        if not dt:
            return False
        # If already naive, return as-is
        if getattr(dt, 'tzinfo', None) is None:
            return dt
        try:
            return dt.astimezone(pytz.UTC).replace(tzinfo=None)
        except Exception:
            # Fallback: strip tzinfo (not ideal, but prevents crashes)
            return dt.replace(tzinfo=None)

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


    
    set_status_to_confirmed=fields.Boolean(string='Set Status to Confirmed', default=False)
    status_to_confirmed_time_user=fields.Datetime(string='Status to Confirmed Time User', default=None)
    set_status_to_confirmed_time=fields.Datetime(string='Set Status to Confirmed Time', default=None)
    status_to_confirmed_error_msg=fields.Text(string='Status to Confirmed Error Message', default=None)
    set_status_to_pick_finished=fields.Boolean(string='Set Status to Pick Finished', default=False)
    status_to_pick_finished_time_user=fields.Datetime(string='Status to Pick Finished Time User', default=None)
    set_status_to_pick_finished_time=fields.Datetime(string='Set Status to Pick Finished Time', default=None)
    status_to_pick_finished_error_msg=fields.Text(string='Status to Pick Finished Error Message', default=None)
    set_outbound_pack_sync=fields.Boolean(string='Set Outbound Pack Sync', default=False)
    set_outbound_pack_sync_time=fields.Datetime(string='Set Outbound Pack Sync Time', default=None)
    outbound_pack_sync_time_user=fields.Datetime(string='Outbound Pack Sync Time User', default=None)
    outbound_pack_sync_error_msg=fields.Text(string='Outbound Pack Sync Error Message', default=None)
    set_logistics_info_sync=fields.Boolean(string='Set Logistics Info Sync', default=False) 
    set_logistics_info_sync_time=fields.Datetime(string='Set Logistics Info Sync Time', default=None)
    logistics_info_sync_time_user=fields.Datetime(string='Logistics Info Sync Time User', default=None)
    logistics_info_sync_error_msg=fields.Text(string='Logistics Info Sync Error Message', default=None)    
    set_outbound_result_sync=fields.Boolean(string='Set Outbound Result Sync', default=False)   
    outbound_result_sync_time_user=fields.Datetime(string='Outbound Result Sync Time User', default=None)
    set_outbound_result_sync_time=fields.Datetime(string='Set Outbound Result Sync Time', default=None)
    outbound_result_sync_error_msg=fields.Text(string='Outbound Result Sync Error Message', default=None)
    # 禾迈-拣货开始
    def action_set_status_to_confirmed(self):
        for order in self:
            if order.project and order.project.name.lower() == 'hoymiles':                
                
                local_time = self.get_local_time('NL', order.confirm_time_server)
                if order.status_to_confirmed_time_user:
                    local_time = order.status_to_confirmed_time_user
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
                            'request_time': fields.Datetime.now(),
                            'request_path': url.url,
                            'request_data': json.dumps(payload),
                            'response_data': response.text
                        })

                        if failed is False:
                            # mark success and store the timestamp (store as naive UTC datetime)
                            order.write({
                                'set_status_to_confirmed': True,
                                'set_status_to_confirmed_time': self._ensure_naive_datetime_or_false(local_time),
                                'status_to_confirmed_error_msg': False,
                            })
                        else:
                            if not order.set_status_to_confirmed:
                                order.write({
                                    'set_status_to_confirmed': False,
                                    'set_status_to_confirmed_time': False,
                                    'status_to_confirmed_error_msg': response.text,
                                })
                        return failed is False
                    else:
                        _logger.error("Token fetch failed: HTTP %s - %s", response.status_code, response.text)
                        # write api log
                        self.env['hoymiles.api.logs'].sudo().create({
                            'request_source': _source,
                            'request_time': fields.Datetime.now(),
                            'request_path': url.url,
                            'request_data': json.dumps(payload),
                            'response_data': response.text,
                            'exception_details': f"HTTP {response.status_code}"
                        })
                        if not order.set_status_to_confirmed:
                            order.write({
                                'set_status_to_confirmed': False,
                                'set_status_to_confirmed_time': False,
                                'status_to_confirmed_error_msg': response.text,
                            })
                        return False

                except requests.exceptions.RequestException as e:
                    _logger.error("Network error during token fetch: %s", str(e))
                    # write api log
                    self.env['hoymiles.api.logs'].sudo().create({
                        'request_source': _source,
                        'request_time': fields.Datetime.now(),
                        'request_path': url.url,
                        'request_data': json.dumps(payload),
                        'response_data': False,
                        'exception_details': str(e)
                    })
                    if not order.set_status_to_confirmed:
                        order.write({
                            'set_status_to_confirmed': False,
                            'set_status_to_confirmed_time': False,
                            'status_to_confirmed_error_msg': str(e),
                        })
                    return False
                except json.JSONDecodeError as e:
                    _logger.error("JSON decode error in token response: %s", str(e))
                    # write api log
                    self.env['hoymiles.api.logs'].sudo().create({
                        'request_source': _source,
                        'request_time': fields.Datetime.now(),
                        'request_path': url.url,
                        'request_data': json.dumps(payload),
                        'response_data': False,
                        'exception_details': str(e)
                    })
                    if not order.set_status_to_confirmed:
                        order.write({
                            'set_status_to_confirmed': False,
                            'set_status_to_confirmed_time': False,
                            'status_to_confirmed_error_msg': str(e),
                        })
                    return False
            return True

    # 禾迈-拣货完成
    def action_set_status_to_pick_finished(self):
        for order in self:
            if order.project and order.project.name.lower() == 'hoymiles':
                local_time = self.get_local_time('NL', order.picking_PICK.date_done)
                if order.status_to_pick_finished_time_user:
                    local_time = order.status_to_pick_finished_time_user
                    
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
                            'request_time': fields.Datetime.now(),
                            'request_path': url.url,
                            'request_data': json.dumps(payload),
                            'response_data': response.text
                        })
                        if failed is False:
                            order.write({
                                'set_status_to_pick_finished': True,
                                'set_status_to_pick_finished_time': self._ensure_naive_datetime_or_false(local_time),
                                'status_to_pick_finished_error_msg': False,
                            })
                        else:
                            if not order.set_status_to_pick_finished:
                                order.write({
                                    'set_status_to_pick_finished': False,
                                    'set_status_to_pick_finished_time': False,
                                    'status_to_pick_finished_error_msg': response.text,
                                })
                        return failed is False
                    else:
                        _logger.error("Token fetch failed: HTTP %s - %s", response.status_code, response.text)
                        # write api log
                        self.env['hoymiles.api.logs'].sudo().create({
                            'request_source': _source,
                            'request_time': fields.Datetime.now(),
                            'request_path': url.url,
                            'request_data': json.dumps(payload),
                            'response_data': response.text,
                            'exception_details': f"HTTP {response.status_code}"
                        })
                        if not order.set_status_to_pick_finished:
                            order.write({
                                'set_status_to_pick_finished': False,
                                'set_status_to_pick_finished_time': False,
                                'status_to_pick_finished_error_msg': response.text,
                            })
                        return False

                except requests.exceptions.RequestException as e:
                    _logger.error("Network error during token fetch: %s", str(e))
                    # write api log
                    self.env['hoymiles.api.logs'].sudo().create({
                        'request_source': _source,
                        'request_time': fields.Datetime.now(),
                        'request_path': url.url,
                        'request_data': json.dumps(payload),
                        'response_data': False,
                        'exception_details': str(e)
                    })
                    if not order.set_status_to_pick_finished:
                        order.write({
                            'set_status_to_pick_finished': False,
                            'set_status_to_pick_finished_time': False,
                            'status_to_pick_finished_error_msg': str(e),
                        })
                    return False
                except json.JSONDecodeError as e:
                    _logger.error("JSON decode error in token response: %s", str(e))
                    # write api log
                    self.env['hoymiles.api.logs'].sudo().create({
                        'request_source': _source,
                        'request_time': fields.Datetime.now(),
                        'request_path': url.url,
                        'request_data': json.dumps(payload),
                        'response_data': False,
                        'exception_details': str(e)
                    })
                    if not order.set_status_to_pick_finished:
                        order.write({
                            'set_status_to_pick_finished': False,
                            'set_status_to_pick_finished_time': False,
                            'status_to_pick_finished_error_msg': str(e),
                        })
                    return False
            return True

    # 禾迈-出库打包
    def action_set_outbound_pack_sync(self):
        for order in self:
            if order.project and order.project.name.lower() == 'hoymiles':
                local_time = self.get_local_time('NL', order.picking_PICK.date_done)
                if order.outbound_pack_sync_time_user:
                    local_time = order.outbound_pack_sync_time_user                                    
                # generate boxPalletSpec (use safe getattr with defaults to avoid errors if fields are missing)                
                boxPalletSpecs = []
                boxPalletSpec = ""
                if order.outbound_order_pack_ids:
                    _logger.debug('Outbound order %s has %d pack(s)', order.id, len(order.outbound_order_pack_ids))
                    irow=1
                    for pack in order.outbound_order_pack_ids:
                        try:
                            # total_quantity is computed on pack; fallback to summing product quantities
                            #total_qty = getattr(pack, 'total_quantity', None)
                            #if total_qty in (None, 0):
                            #    total_qty = sum(getattr(p, 'quantity', 0) for p in getattr(pack, 'pack_product_ids', []) or []) or 0

                            # pack_type is stored on the order level; use that as fallback and uppercase it
                            pack_type = (getattr(pack, 'pack_type', None) or getattr(order, 'pack_type', '') or '').upper()
                            pack_length = getattr(pack, 'length', None) or 0
                            pack_width = getattr(pack, 'width', None) or 0
                            pack_height = getattr(pack, 'height', None) or 0
                            gross_weight = getattr(pack, 'gross_weight', None) or 0
                            net_weight = getattr(pack, 'net_weight', None) or 0
                            pack_count = getattr(pack, 'count', None) or 1
                            pack_products = getattr(pack, 'product_description', None) or ''

                            # Format spec using pack_number to uniquely identify the pack
                            spec_str = f"({irow}) {pack_type} {pack_count}*{pack_length}*{pack_width}*{pack_height}cm GW {gross_weight}]"
                            boxPalletSpecs.append(spec_str)
                            irow += 1
                        except Exception:
                            # keep going; malformed pack records shouldn't stop payload generation
                            _logger.exception('Failed to read pack fields for outbound pack spec')

                    # If packs exist but no spec strings were produced (edge case), create a fallback spec per pack
                    if order.outbound_order_pack_ids and not boxPalletSpecs:
                        _logger.debug('No boxPalletSpecs generated for order %s; building fallback specs', order.id)
                        irow = 1
                        for pack in order.outbound_order_pack_ids:
                            try:
                                total_qty = getattr(pack, 'total_quantity', 0) or 0
                                pack_type = (getattr(pack, 'pack_type', None) or getattr(order, 'pack_type', '') or '').upper()
                                # Use pack_type first for the spec and include pack_number as identifier in parentheses
                                # spec_str = f"({irow}) {pack_type} {pack_count}*{getattr(pack, 'length', 0)}*{getattr(pack, 'width', 0)}*{getattr(pack, 'height', 0)}cm GW {getattr(pack, 'gross_weight', 0)} PRODUCTS[{pack_products}]"
                                spec_str = f"({irow}) {pack_type} {pack_count}*{getattr(pack, 'length', 0)}*{getattr(pack, 'width', 0)}*{getattr(pack, 'height', 0)}cm GW {getattr(pack, 'gross_weight', 0)}"
                                boxPalletSpecs.append(spec_str)
                                irow += 1
                            except Exception:
                                _logger.exception('Fallback spec build failed for pack %s on order %s', getattr(pack, 'id', False), order.id)
                    irow += 1
                if boxPalletSpecs:
                    boxPalletSpec = "+".join(boxPalletSpecs)
                    

                # sum gross/net weights from packs if available
                gross_sum = 0
                net_sum = 0
                if order.outbound_order_pack_ids:
                    gross_sum = sum((getattr(p, 'gross_weight', 0)*getattr(p, 'count', 1) or 0) for p in order.outbound_order_pack_ids)
                    net_sum = sum((getattr(p, 'net_weight', 0)*getattr(p, 'count', 1) or 0) for p in order.outbound_order_pack_ids)
                    
                    
                    
                payload = {
                    "thirdPartyWsCode": "WD",
                    "thirdPartyWsName": "WD warehouse",
                    "wsOpOrderNo": order.picking_PICK.name if order.picking_PICK else "",                    
                    "reference": order.reference,
                    "grossWeight": gross_sum,
                    "netWeight": net_sum,
                    "boxPalletSpec": f"{boxPalletSpec}",
                    "packingFinishedTime": local_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "packingMethod": (getattr(order, 'pack_type', '') or '').upper(),
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
                    "serials": [],
                    "pickupCode": order.load_ref or "",
                    "pickupWarehouse": "WD",
                }

                if order.picking_PICK:
                    # Group moves by outbound_order_product_id when available, otherwise by product
                    groups = {}
                    for move in order.picking_PICK.move_ids:
                        try:
                            prod = getattr(move, 'product_id', None)
                            oop = getattr(move, 'outbound_order_product_id', None)
                            # grouping key: prefer outbound_order_product_id (tuple prefix to avoid collisions)
                            if oop and getattr(oop, 'id', False):
                                key = ('oop', int(oop.id))
                                oop_id = int(oop.id)
                            else:
                                key = ('prod', int(prod.id) if prod else 0)
                                oop_id = False

                            # quantity on stock.move may be named 'product_uom_qty' or 'quantity' or 'product_qty'
                            qty = getattr(move, 'quantity', None)
                            if qty is None:
                                qty = getattr(move, 'product_uom_qty', None)
                            if qty is None:
                                qty = getattr(move, 'product_qty', None)
                            if qty is None:
                                qty = 0
                            try:
                                qty_val = float(qty)
                            except Exception:
                                qty_val = 0.0

                            item_num = ''
                            try:
                                if prod:
                                    item_num = (getattr(prod, 'barcode', None) or getattr(prod, 'default_code', '') or '')
                            except Exception:
                                _logger.exception('Failed to read product identifier for move %s', getattr(move, 'id', False))

                            # collect serials for this move
                            serials = set()
                            for move_line in getattr(move, 'move_line_ids', []) or []:
                                try:
                                    lot = getattr(move_line, 'lot_id', None) or getattr(move_line, 'lot_name', None)
                                    serial_name = getattr(lot, 'name', None) if hasattr(lot, 'name') else (lot or '')
                                    if serial_name:
                                        serials.add(str(serial_name))
                                except Exception:
                                    _logger.exception('Failed to read move_line serial/lot for move %s', getattr(move, 'id', False))

                            if key not in groups:
                                groups[key] = {
                                    'itemNum': item_num,
                                    'qty': 0.0,
                                    'serials': set(),
                                    'oop': oop_id,
                                }
                            groups[key]['qty'] += qty_val
                            groups[key]['serials'].update(serials)
                        except Exception:
                            _logger.exception('Failed to read move fields for outbound pack lines')

                    # Convert groups into payload lines and serials (deduplicated)
                    for g, val in groups.items():
                        try:
                            received_qty = int(val['qty']) if val['qty'] is not None else 0
                        except Exception:
                            received_qty = 0
                        line = {
                            'itemNum': val.get('itemNum', ''),
                            'receivedQuantity': received_qty,
                        }
                        #if val.get('oop'):
                        #    line['outboundOrderProductId'] = val.get('oop')
                        payload['lines'].append(line)
                        for s in sorted(val.get('serials') or []):
                            payload['serials'].append({'serialNumber': s})

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
                        if failed is False:
                            order.write({
                                'set_outbound_pack_sync': True,
                                'set_outbound_pack_sync_time': self._ensure_naive_datetime_or_false(local_time),
                                'outbound_pack_sync_error_msg': False,
                            })
                            return True
                        else:
                            if not order.set_outbound_pack_sync:
                                order.write({
                                    'set_outbound_pack_sync': False,
                                    'set_outbound_pack_sync_time': False,
                                    'outbound_pack_sync_error_msg': response.text,
                                })
                            return False
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
                        if not order.set_outbound_pack_sync:
                            order.write({
                                'set_outbound_pack_sync': False,
                                'set_outbound_pack_sync_time': False,
                                'outbound_pack_sync_error_msg': response.text,
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
                    if not order.set_outbound_pack_sync:
                        order.write({
                            'set_outbound_pack_sync': False,
                            'set_outbound_pack_sync_time': False,
                            'outbound_pack_sync_error_msg':  str(e),
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
                    if not order.set_outbound_pack_sync:
                        order.write({
                            'set_outbound_pack_sync': False,
                            'set_outbound_pack_sync_time': False,
                            'outbound_pack_sync_error_msg':  str(e),
                        })  
                    return False
            return True

    # 禾迈-出库物流信息
    def action_set_logistics_info_sync(self):
        for order in self:
            if order.project and order.project.name.lower() == 'hoymiles':
                local_time = self.get_local_time('NL', order.picking_PICK.date_done)
                if order.logistics_info_sync_time_user:
                    local_time = order.logistics_info_sync_time_user
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
                        if failed is False:
                            order.write({
                                'set_logistics_info_sync': True,
                                'set_logistics_info_sync_time': self._ensure_naive_datetime_or_false(local_time),
                                'logistics_info_sync_error_msg': False,
                            })
                        else:
                            if not order.set_logistics_info_sync:
                                order.write({
                                    'set_logistics_info_sync': False,
                                    'set_logistics_info_sync_time': False,
                                    'logistics_info_sync_error_msg': response.text,
                                })
                        return failed is False
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
                        if not order.set_logistics_info_sync:
                            order.write({
                                'set_logistics_info_sync': False,
                                'set_logistics_info_sync_time': False,
                                'logistics_info_sync_error_msg': response.text,
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
                    if not order.set_logistics_info_sync:
                        order.write({
                            'set_logistics_info_sync': False,
                            'set_logistics_info_sync_time': False,
                            'logistics_info_sync_error_msg': str(e),
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
                    if not order.set_logistics_info_sync:
                        order.write({
                            'set_logistics_info_sync': False,
                            'set_logistics_info_sync_time': False,
                            'logistics_info_sync_error_msg': str(e),
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
                    if order.outbound_result_sync_time_user:
                        local_time = order.outbound_result_sync_time_user
                        
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
                                if failed is False:
                                    order.write({
                                        'set_outbound_result_sync': True,
                                        'set_outbound_result_sync_time': self._ensure_naive_datetime_or_false(local_time),
                                        'outbound_result_sync_error_msg': False,
                                    })
                                else:
                                    if not order.set_outbound_result_sync:
                                        order.write({
                                            'set_outbound_result_sync': False,
                                            'set_outbound_result_sync_time': False,
                                            'outbound_result_sync_error_msg': response.text,
                                        })
                                return failed is False
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
                                if not order.set_outbound_result_sync:
                                    order.write({
                                        'set_outbound_result_sync': False,
                                        'set_outbound_result_sync_time': False,
                                        'outbound_result_sync_error_msg': response.text,
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
                            if not order.set_outbound_result_sync:
                                order.write({
                                    'set_outbound_result_sync': False,
                                    'set_outbound_result_sync_time': False,
                                    'outbound_result_sync_error_msg': str(e),
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
                            if not order.set_outbound_result_sync:
                                order.write({
                                    'set_outbound_result_sync': False,
                                    'set_outbound_result_sync_time': False,
                                    'outbound_result_sync_error_msg': str(e),
                                })
                            return False
                    return True




