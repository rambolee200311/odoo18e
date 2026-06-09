# -*- coding: utf-8 -*-

import copy
import json
import logging
import requests

from odoo import _, fields, models
from odoo.exceptions import UserError
import hashlib
_logger = logging.getLogger(__name__)
class InboundOrderSunrise(models.Model):
    _inherit = "world.depot.inbound.order"

    set_sunrise_inbound_sync = fields.Boolean(string="Set Sunrise Inbound Sync", default=False, copy=False, index=True)
    set_sunrise_inbound_sync_time = fields.Datetime(string="Sunrise Inbound Sync Time", copy=False)
    sunrise_inbound_sync_error_msg = fields.Text(string="Sunrise Inbound Sync Error Msg", copy=False)
    sunrise_inbound_task_number = fields.Char(string="Sunrise Inbound Task Number", copy=False, index=True)

    def get_sunrise_api_config(self, api_type):
        config_model = self.env["sunrise.api.config"]
        config = config_model.sudo().search([
            ("api_type", "=", api_type),
            ("active", "=", True),
        ], limit=1)
        if not config:
            raise UserError(_("Please configure an active Sunrise U8C %s API config.") % api_type)
        return config

    def get_sunrise_field_value(self, record, field_name, default=False):
        if not record or field_name not in record._fields:
            return default
        value = record[field_name]
        if hasattr(value, "display_name"):
            return value.display_name or default
        return value or default

    def get_sunrise_inbound_parentvo(self, config):
        if not config.parameters_json:
            parameters = {}
        else:
            try:
                parameters = json.loads(config.parameters_json)
            except ValueError as error:
                raise UserError(_("Sunrise API config parameters_json is invalid JSON: %s") % error)
            if not isinstance(parameters, dict):
                raise UserError(_("Sunrise API config parameters_json must be a JSON object."))

        parent_parameters = parameters.get("parentvo") if isinstance(parameters.get("parentvo"), dict) else {}
        parentvo = {
            "cbiztype": "CG02",
            "coperatorid": config.usercode,
            "cwarehouseid": "99",
            "pk_calbody": "CYJKHL",
            "pk_corp": "CYJKHL",
            "cdispatcherid": "101",
        }
        for key in ("cbiztype", "coperatorid", "cwarehouseid", "pk_calbody", "pk_corp", "cdispatcherid"):
            if key in parameters:
                parentvo[key] = parameters[key]
        parentvo.update(parent_parameters)
        return parentvo, parameters

    def get_u8c_inbound_detail_line(self, move_line):
        detail_line = move_line.inbound_order_product_pallet_id
        if not detail_line:
            raise UserError(_("Move line %s has no inbound product detail for Sunrise sync.") % move_line.id)
        return detail_line

    def build_u8c_inbound_payload(self, config=False):
        result = []
        for rec in self:
            api_config = config or rec.get_sunrise_api_config("inbound")
            parentvo, parameters = rec.get_sunrise_inbound_parentvo(api_config)
            picking = rec.stock_picking_id
            if not picking:
                raise UserError(_("Inbound order %s has no stock picking.") % (rec.billno or rec.reference))
            if picking.state != "done":
                raise UserError(_("Inbound picking %s must be done before syncing to U8C.") % picking.name)

            move_lines = picking.move_line_ids.filtered(lambda line: line.quantity > 0)
            if not move_lines:
                raise UserError(_("Inbound picking %s has no move lines to sync.") % picking.name)

            parentvo["vuserdef3"] = rec.cntr_no or ""

            child_parameters = parameters.get("childrenvo") if isinstance(parameters.get("childrenvo"), dict) else {}
            locator_parameters = parameters.get("locator") if isinstance(parameters.get("locator"), dict) else {}
            childrenvo = []
            for move_line in move_lines:
                detail_line = rec.get_u8c_inbound_detail_line(move_line)
                product = move_line.product_id
                product_barcode = product.barcode
                product_barcode = product_barcode.split("-", 1)[0]
                if not product_barcode:
                    raise UserError(_("Product %s has no internal reference for U8C cinventoryid.") % product.display_name)
                location_code = detail_line.inbound_order_product_id.pallet_no
                if not location_code:
                    raise UserError(_("Inbound_detail_line%s has no destination location code.") % move_line.id)

                locator = dict(locator_parameters)
                locator.update({
                    "cspaceid": location_code,
                    "ninspacenum": detail_line.ninnum,
                    "ninspaceassistnum": detail_line.u8_aux_qty,
                })
                child = dict(child_parameters)
                child.update({
                    "cprojectid": detail_line.cprojectid,
                    "ndiscounttaxtype": detail_line.ndiscounttaxtype,
                    "cinventoryid": product_barcode,
                    "castunitid": detail_line.castunitid,
                    "ninnum": detail_line.ninnum,
                    "csourcetype": "23",
                    "vsourcebillcode": detail_line.vsourcebillcode,
                    "vsourcerowno": detail_line.vsourcerowno,
                    "vbatchcode": move_line.lot_id.name or detail_line.lot_name or "",
                    "locator": [locator],
                })
                childrenvo.append(child)

            result.append({
                "url": api_config.data_url,
                "pathInfo": api_config.path_info,
                "trantype": api_config.trantype,
                "indata": {
                    "GeneralBillVO": [{
                        "parentvo": parentvo,
                        "childrenvo": childrenvo,
                    }],
                },
            })
        return result[0] if len(result) == 1 else result

    def get_sunrise_masked_request_data(self, headers, payload):
        masked_headers = copy.deepcopy(headers)
        if "password" in masked_headers:
            masked_headers["password"] = "***"
        return json.dumps({
            "headers": masked_headers,
            "payload": payload,
        }, ensure_ascii=False)

    def get_u8c_password(self, password):
        return hashlib.md5(
            (password or "").encode("utf-8")
        ).hexdigest()
#按钮入口
    def action_sync_u8c_inbound(self):
        if len(self) != 1:
            raise UserError(_("Please sync one inbound order at a time."))
        log_model = self.env["sunrise.api.log"]
        for rec in self:
            config = rec.get_sunrise_api_config("inbound")
            payload = rec.build_u8c_inbound_payload(config=config)
            request_source = "Sunrise Inbound U8C Sync"
            headers = {
                "Content-Type": "application/json",
                "usercode": config.usercode,
                "password":config.password,
                "trantype": config.trantype,
                "system": config.system,
            }
            request_time = fields.Datetime.now()
            response_time = False
            response_text = False
            status = "failed"
            error_message = False
            exception_details = False
            task_number = False
            try:
                response = requests.post(
                    config.url,
                    headers=headers,
                    json=payload,
                    timeout=config.timeout or 10,
                )
                response_time = fields.Datetime.now()
                response_text = response.text
                if response.status_code != 200:
                    error_message = response.text
                    exception_details = "HTTP %s" % response.status_code
                else:
                    try:
                        response_data = response.json() if response.text else {}
                    except ValueError as error:
                        error_message = response.text
                        exception_details = str(error)
                    else:
                        if response_data.get("status") == "success":
                            status = "success"
                            task_number = response_data.get("taskNumber") or response_data.get("task_number")
                            rec.write({
                                "set_sunrise_inbound_sync": True,
                                "set_sunrise_inbound_sync_time": response_time,
                                "sunrise_inbound_sync_error_msg": False,
                                "sunrise_inbound_task_number": task_number,
                            })
                        else:
                            error_message = response_data.get("errsomsg") or response.text
                            exception_details = response_data.get("stackTrace") or error_message
            except Exception  as error:
                response_time = fields.Datetime.now()
                error_message = str(error)
                exception_details = str(error)

            log = log_model.sudo().create({
                "request_source": request_source,
                "request_time": request_time,
                "request_path": config.url,
                "request_data": rec.get_sunrise_masked_request_data(headers, payload),
                "response_data": response_text,
                "exception_details": exception_details,
            })
            _logger.error("LOG ID=%s", log.id)
            if status != "success":
                rec.write({
                    "set_sunrise_inbound_sync": False,
                    "set_sunrise_inbound_sync_time": response_time or fields.Datetime.now(),
                    "sunrise_inbound_sync_error_msg": error_message or exception_details,
                })
                self.env.cr.commit()
                raise UserError(_("Sunrise U8C inbound sync failed: %s") % (error_message or exception_details))

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Sunrise U8C inbound sync completed."),
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.act_window",
                    "name": _("Inbound Order"),
                    "res_model": "world.depot.inbound.order",
                    "res_id": self[:1].id,
                    "view_mode": "form",
                    "views": [(False, "form")],
                    "target": "current",
                },
            },
        }
