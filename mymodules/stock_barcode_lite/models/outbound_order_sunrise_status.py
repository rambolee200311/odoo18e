# -*- coding: utf-8 -*-

import copy
import hashlib
import json
import logging
from datetime import date, datetime

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class OutboundOrderSunrise(models.Model):
    _inherit = "world.depot.outbound.order"

    set_sunrise_outbound_sync = fields.Boolean(string="Set Sunrise Outbound Sync", default=False, copy=False, index=True)
    set_sunrise_outbound_sync_time = fields.Datetime(string="Sunrise Outbound Sync Time", copy=False)
    sunrise_outbound_sync_error_msg = fields.Text(string="Sunrise Outbound Sync Error Msg", copy=False)
    sunrise_outbound_task_number = fields.Char(string="Sunrise Outbound Task Number", copy=False, index=True)

    def get_sunrise_api_config(self, api_type):
        config_model = self.env["sunrise.api.config"]
        config = config_model.sudo().search([
            ("api_type", "=", api_type),
            ("active", "=", True),
        ], limit=1)
        if not config:
            raise UserError(_("Please configure an active Sunrise U8C %s API config.") % api_type)
        return config

    def get_sunrise_date_text(self, value):
        if not value:
            return False
        if isinstance(value, str):
            return value
        if isinstance(value, datetime):
            return fields.Date.to_string(value.date())
        if isinstance(value, date):
            return fields.Date.to_string(value)
        return str(value)

    def get_outbound_sync_picking(self):
        for rec in self:
            if not rec.picking_Out:
                raise UserError(_("Outbound order %s has no outbound picking.") % (rec.billno or rec.reference))
            if rec.picking_Out.state != "done":
                raise UserError(_("Outbound picking %s must be done before syncing to U8C.") % rec.picking_Out.name)
            return rec.picking_Out
        return False

    def get_sunrise_outbound_parentvo(self, config, rec):
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
            "cbiztype": "XS01",
            "coperatorid": config.usercode,
            "cdispatcherid": "201",
        }
        for key in ("cbiztype", "coperatorid", "cwarehouseid", "pk_calbody", "pk_corp", "cdispatcherid", "ccustomerid"):
            if key in parameters:
                parentvo[key] = parameters[key]
        parentvo.update(parent_parameters)

        missing_keys = [key for key in ("cwarehouseid", "pk_calbody", "pk_corp", "ccustomerid") if not parentvo.get(key)]
        if missing_keys:
            raise UserError(_("Sunrise outbound parentvo is missing required config keys: %s") % ", ".join(missing_keys))

        delivery_method_map = {
            "truck": "truck",
            "pickup": "pickup",
            "parcel": "parcel",
        }
        parentvo.update({
            "dbilldate": self.get_sunrise_date_text(rec.date),
            "vnote": rec.load_ref or rec.remark or rec.reference or "",
            #"vuserdef14": rec.load_ref or "",
            "vuserdef17": self.get_sunrise_date_text(rec.p_date),
            #"vuserdef5": delivery_method_map.get(rec.delivery_method, rec.delivery_method or ""),
            "ccustomerid": self.unload_company.name,
        })
        if not parentvo.get("vuserdef6"):
            parentvo.pop("vuserdef6", None)
        return parentvo, parameters

    def get_u8c_outbound_detail_line(self, move_line):
        detail_line_id = move_line.move_id.outbound_order_product_id
        if not detail_line_id:
            raise UserError(_("Move line %s has no outbound product detail for Sunrise sync.") % move_line.id)

        detail_line = self.env["world.depot.outbound.order.product"].sudo().browse(detail_line_id).exists()
        if not detail_line:
            raise UserError(
                _("Move line %s outbound product detail %s was not found.") % (move_line.id, detail_line_id)
            )
        return detail_line

    def build_u8c_outbound_payload(self, config=False):
        result = []
        for rec in self:
            api_config = config or rec.get_sunrise_api_config("outbound")
            parentvo, parameters = rec.get_sunrise_outbound_parentvo(api_config, rec)
            picking = rec.get_outbound_sync_picking()
            move_lines = picking.move_line_ids.filtered(lambda line: line.quantity > 0)
            if not move_lines:
                raise UserError(_("Outbound picking %s has no move lines to sync.") % picking.name)

            child_parameters = parameters.get("childrenvo") if isinstance(parameters.get("childrenvo"), dict) else {}
            locator_parameters = parameters.get("locator") if isinstance(parameters.get("locator"), dict) else {}
            childrenvo = []
            biz_date = rec.get_sunrise_date_text(rec.o_date or rec.picking_Out_date or rec.date)

            for move_line in move_lines:
                detail_line = rec.get_u8c_outbound_detail_line(move_line)
                product = move_line.product_id
                product_barcode = product.barcode
                product_barcode = product_barcode.split("-", 1)[0]
                if not product_barcode:
                    raise UserError(_("Product %s has no internal reference for U8C cinventoryid.") % product.display_name)

                location_code = detail_line.pallet_no
                if not location_code:
                    raise UserError(_("Move line %s has no source location code for U8C locator.") % move_line.id)

                locator = dict(locator_parameters)
                locator.update({
                    "cspaceid": location_code,
                    "noutspacenum": detail_line.ninnum,
                })

                child = dict(child_parameters)
                child.update({
                    "cprojectid": detail_line.cprojectid,
                    "vsourcebillcode": detail_line.vsourcebillcode,
                    "vsourcerowno": detail_line.vsourcerowno,
                    "csourcetype": "4331",
                    "noutnum": detail_line.ninnum,
                    "nshouldoutnum": detail_line.ninnum,
                    "cinventoryid": product_barcode,
                    "vbatchcode": move_line.lot_id.name or detail_line.lot_name or "",
                    "dbizdate": biz_date,
                    "vnotebody": detail_line.remark or rec.remark or rec.reference or "",
                    "castunitid": detail_line.castunitid,
                    "locator": [locator],
                })
                childrenvo.append(child)

            result.append({
                    "GeneralBillVO": [{
                        "parentvo": parentvo,
                        "childrenvo": childrenvo,
                    }],

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

    def action_sync_u8c_outbound(self):
        if len(self) != 1:
            raise UserError(_("Please sync one outbound order at a time."))

        log_model = self.env["sunrise.api.log"]
        for rec in self:
            config = rec.get_sunrise_api_config("outbound")
            payload = rec.build_u8c_outbound_payload(config=config)
            headers = {
                "Content-Type": "application/json",
                "usercode": config.usercode,
                "password": config.password,
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
                                "set_sunrise_outbound_sync": True,
                                "set_sunrise_outbound_sync_time": response_time,
                                "sunrise_outbound_sync_error_msg": False,
                                "sunrise_outbound_task_number": task_number,
                            })
                        else:
                            error_message = response_data.get("errsomsg") or response.text
                            exception_details = response_data.get("stackTrace") or error_message
            except Exception as error:
                response_time = fields.Datetime.now()
                error_message = str(error)
                exception_details = str(error)

            log = log_model.create({
                "request_source": "Sunrise Outbound U8C Sync",
                "request_time": request_time,
                "request_path": config.url,
                "request_data": rec.get_sunrise_masked_request_data(headers, payload),
                "response_data": response_text,
                "exception_details": exception_details,
            })
            _logger.error("LOG ID=%s", log.id)

            if status != "success":
                rec.write({
                    "set_sunrise_outbound_sync": False,
                    "set_sunrise_outbound_sync_time": response_time or fields.Datetime.now(),
                    "sunrise_outbound_sync_error_msg": error_message or exception_details,
                })
                self.env.cr.commit()
                raise UserError(_("Sunrise U8C outbound sync failed: %s") % (error_message or exception_details))

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Sunrise U8C outbound sync completed."),
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.act_window",
                    "name": _("Outbound Order"),
                    "res_model": "world.depot.outbound.order",
                    "res_id": self[:1].id,
                    "view_mode": "form",
                    "views": [(False, "form")],
                    "target": "current",
                },
            },
        }
