import json
import logging

import requests
from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

class TransferOrderStatus(models.Model):
    _inherit = 'world.depot.transfer.order'

    set_transfer_result_sync = fields.Boolean(string="Set Transfer Result Sync", default=False)
    set_transfer_result_sync_time = fields.Datetime(string="Transfer Result Sync Time", readonly=True)
    transfer_result_sync_error_msg = fields.Text(string="Transfer Result Sync Error Msg", readonly=True)

    def action_set_transfer_result_sync(self):
        for order in self:
            # 仅 Hoymiles 项目才同步
            if not (order.project and order.project.name and order.project.name.lower() == 'hoymiles'):
                continue

            payload = {
                "thirdPartyWsCode": "WD",
                "reference": order.reference,
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

            for line in order.line_ids:
                line_data = {
                    "itemNum": line.product.barcode if line.product else line.product.default_code or '',
                    "quantity": line.quantity if line.quantity else 0,
                }
                payload["lines"].append(line_data)
            if not order.stock_picking_id:
                raise UserError("No picking found for this transfer order.")
            # 所有picking
            pickings = order.mapped('stock_picking_id')
            lot_names = pickings.mapped('move_line_ids.lot_id.name')
            lot_names = [x for x in lot_names if x]
            payload["serials"] = [{"serialNumber": n} for n in lot_names]

            # 获取 token
            token = order.env['hoymiles.token.utils'].get_oauth_token()
            if not token:
                raise UserError("Failed to retrieve OAuth token.")

            url_rec = self.env['hoymiles.api.urls'].search([('name', '=', 'transfer-result-sync')], limit=1)
            if not url_rec or not url_rec.url:
                raise UserError("API URL configuration is missing.")

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {token}'
            }

            _source = 'Transfer Result'

            try:
                response = requests.post(
                    url_rec.url,
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=10
                )

                self.env['hoymiles.api.logs'].sudo().create({
                    'request_source': _source,
                    'request_time': datetime.now(),
                    'request_path': url_rec.url,
                    'request_data': json.dumps(payload),
                    'response_data': response.text,
                })
                if response.status_code == 200:
                    response_data = {}
                    try:
                        response_data = response.json() if response.text else {}
                    except Exception:
                        response_data = {}

                    failed = response_data.get('failed')

                    if not failed:
                        order.write({
                            'set_transfer_result_sync': True,
                            'set_transfer_result_sync_time': datetime.now(),
                            'transfer_result_sync_error_msg': False,
                        })
                    else:
                        if not order.set_transfer_result_sync:
                            order.write({
                                'set_transfer_result_sync': False,
                                'set_transfer_result_sync_time': datetime.now(),
                                'transfer_result_sync_error_msg': response.text,
                            })
                    return failed

                # 非 200
                _logger.error("Transfer result sync failed: HTTP %s - %s", response.status_code, response.text)
                self.env['hoymiles.api.logs'].sudo().create({
                    'request_source': _source,
                    'request_time': datetime.now(),
                    'request_path': url_rec.url,
                    'request_data': json.dumps(payload),
                    'response_data': response.text,
                    'exception_details': f"HTTP {response.status_code}"
                })
                if not order.set_transfer_result_sync:
                    order.write({
                        'set_transfer_result_sync': False,
                        'set_transfer_result_sync_time': datetime.now(),
                        'transfer_result_sync_error_msg': response.text,
                    })
                return False

            except requests.exceptions.RequestException as e:
                _logger.error("Network error during transfer result sync: %s", str(e))
                self.env['hoymiles.api.logs'].sudo().create({
                    'request_source': _source,
                    'request_time': datetime.now(),
                    'request_path': url_rec.url,
                    'request_data': json.dumps(payload),
                    'response_data': False,
                    'exception_details': str(e)
                })
                if not order.set_transfer_result_sync:
                    order.write({
                        'set_transfer_result_sync': False,
                        'set_transfer_result_sync_time': datetime.now(),
                        'transfer_result_sync_error_msg': str(e),
                    })
                return False

            except json.JSONDecodeError as e:
                _logger.error("JSON decode error in transfer result response: %s", str(e))
                self.env['hoymiles.api.logs'].sudo().create({
                    'request_source': _source,
                    'request_time': datetime.now(),
                    'request_path': url_rec.url,
                    'request_data': json.dumps(payload),
                    'response_data': False,
                    'exception_details': str(e)
                })
                if not order.set_transfer_result_sync:
                    order.write({
                        'set_transfer_result_sync': False,
                        'set_transfer_result_sync_time': datetime.now(),
                        'transfer_result_sync_error_msg': str(e),
                    })
                return False

        return True
