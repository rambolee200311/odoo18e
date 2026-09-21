# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime, timezone

from odoo import http, fields
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class PortbaseWebhookController(http.Controller):

    def parse_portbase_datetime(self, value):
        if not value:
            return False
        text_value = str(value).strip()
        if text_value.endswith("Z"):
            text_value = text_value[:-1] + "+00:00"
        try:
            dt_value = datetime.fromisoformat(text_value)
        except ValueError:
            return False
        if dt_value.tzinfo:
            dt_value = dt_value.astimezone(timezone.utc).replace(tzinfo=None)
        return fields.Datetime.to_string(dt_value)

    def parse_portbase_date(self, value):
        dt_text = self.parse_portbase_datetime(value)
        if not dt_text:
            return False
        dt_value = fields.Datetime.from_string(dt_text)
        return fields.Date.to_string(dt_value.date())

    def build_line_map(self, lines):
        line_map = {}
        for line in lines or []:
            equipment_number = line.get("equipmentNumber")
            if equipment_number:
                line_map[equipment_number] = line
        return line_map

    def build_inspection_map(self, inspection_items):
        inspection_map = {}
        for line in inspection_items or []:
            status = line.get("status")
            if not status:
                continue
            equipment_numbers = line.get("equipmentNumbers") or []
            single_equipment_number = line.get("equipmentNumber")
            if single_equipment_number:
                equipment_numbers.append(single_equipment_number)
            if not equipment_numbers:
                inspection_map["__global__"] = status
            for equipment_number in equipment_numbers:
                if equipment_number:
                    inspection_map[equipment_number] = status
        return inspection_map

    def build_inland_operator_map(self, nominated_inland_operators):
        operator_map = {}
        for line in nominated_inland_operators or []:
            equipment_number = line.get("equipmentNumber")
            if equipment_number:
                operator_map[equipment_number] = line.get("inlandOperatorFullName") or False
        return operator_map

    @http.route("/portbase/webhook", type="http", auth="none", methods=["POST"], csrf=False)
    def portbase_webhook(self, **kwargs):
        raw_data = request.httprequest.data or b"{}"
        raw_text = raw_data.decode("utf-8", errors="replace")
        payload = json.loads(raw_text) if raw_text else {}

        if isinstance(payload, dict):
            events = [payload]
        elif isinstance(payload, list):
            events = [x for x in payload if isinstance(x, dict)]
        else:
            events = []
        #self.portbase_webhook_t()
        if not events:
            return Response("invalid payload", status=400, content_type="text/plain;charset=utf-8")

        env = request.env
        ok_count = 0
        fail_count = 0

        for event in events:
            event_id = event.get("id") or False
            bl_number = event.get("blNumber") or (event.get("billOfLading") or {}).get("blNumber") or False

            # 防重复（查询按你规范用 sudo）
            exists = env["portbase.webhook.log"].sudo().search([("event_id", "=", event_id)],
                                                               limit=1) if event_id else False
            if exists:
                continue

            log = env["portbase.webhook.log"].sudo().create({
                "event_id": event_id,
                "event_type": event.get("eventType") or False,
                "tracking_id": event_id,
                "bl_number": bl_number,
                "reference_number": event.get("referenceNumber") or False,
                "request_ip": request.httprequest.headers.get("X-Forwarded-For") or request.httprequest.remote_addr,
                "request_headers": json.dumps(dict(request.httprequest.headers), ensure_ascii=False),
                "raw_payload": json.dumps(event, ensure_ascii=False),
                "process_status": "new",
            })

            try:
                log.write({"process_status": "done", "process_message": "processed"})
                ok_count += 1
            except Exception as err:
                log.write({"process_status": "error", "process_message": str(err)})
                fail_count += 1

        return Response(f"OK: {ok_count}, FAIL: {fail_count}", status=200, content_type="text/plain;charset=utf-8")
    # def portbase_webhook_t(self, **kwargs):
    #     try:
    #         raw_data = request.httprequest.data or b"{}"
    #         payload = json.loads(raw_data.decode("utf-8"))
    #         if isinstance(payload, list):
    #             payload = payload[0] if payload else {}
    #
    #         bill_of_lading = payload.get("billOfLading") or {}
    #         bl_number = payload.get("blNumber") or bill_of_lading.get("blNumber")
    #         if not bl_number:
    #             return Response("missing bl_number", status=400, content_type="text/plain;charset=utf-8")
    #
    #         vessel_visit = bill_of_lading.get("vesselVisit") or {}
    #         port_visit = (vessel_visit.get("visitDeclaration") or {}).get("portVisit") or {}
    #         commercial_releases = bill_of_lading.get("commercialReleases") or []
    #         hinterland_terminal_data = bill_of_lading.get("hinterlandTerminalData") or []
    #         inspection_items = bill_of_lading.get("inspectionItems") or []
    #         discharge_reports = bill_of_lading.get("dischargeReports") or []
    #         transport_equipments = bill_of_lading.get("transportEquipments") or []
    #         nominated_inland_operators = payload.get("nominatedInlandOperators") or []
    #
    #         env_waybill = request.env["world.depot.waybill"]
    #         waybill_ids = env_waybill.sudo().search(
    #             [("bl_number", "=", bl_number), ("state", "!=", "cancel")], limit=1
    #         ).ids
    #         if not waybill_ids:
    #             _logger.warning("portbase webhook skip, waybill not found, bl_number=%s", bl_number)
    #             return Response("OK", status=200, content_type="text/plain;charset=utf-8")
    #
    #         waybill = env_waybill.browse(waybill_ids[0])
    #
    #         waybill_vals = {
    #             "eta": self.parse_portbase_date(port_visit.get("etaPort")),
    #             "ata": self.parse_portbase_date(port_visit.get("ataPort")),
    #             "is_arrived": bool(port_visit.get("ataPort") or vessel_visit.get("visitStatus") in ("ARRIVED", "DEPARTED")),
    #             "release_received": bool(commercial_releases),
    #             "customs_status": bill_of_lading.get("customsStatus") or False,
    #             "portbase_visit_status": vessel_visit.get("visitStatus") or False,
    #             "portbase_last_sync_time": fields.Datetime.now(),
    #             #"update_source": "api",
    #         }
    #         if "voyage_no" in waybill._fields:
    #             waybill_vals["voyage_no"] = vessel_visit.get("crn") or False
    #         if "portbase_tracking_id" in waybill._fields:
    #             waybill_vals["portbase_tracking_id"] = payload.get("id") or waybill.portbase_tracking_id or False
    #         user = request.env.ref('base.user_admin')
    #         waybill.with_user(user).write(waybill_vals)
    #         waybill.with_user(user).message_post(body="Portbase webhook Update", subtype_xmlid="mail.mt_note")
    #
    #         release_map = self.build_line_map(commercial_releases)
    #         gate_out_map = self.build_line_map(hinterland_terminal_data)
    #         discharge_map = self.build_line_map(discharge_reports)
    #         equipment_map = self.build_line_map(transport_equipments)
    #         inspection_map = self.build_inspection_map(inspection_items)
    #         operator_map = self.build_inland_operator_map(nominated_inland_operators)
    #
    #         env_container = request.env["world.depot.waybill.container"].with_user(user)
    #         container_ids = env_container.sudo().search([("waybill_id", "=", waybill.id)]).ids
    #         containers = env_container.browse(container_ids)
    #
    #         for container in containers:
    #             container_number = container.container_number
    #             release_line = release_map.get(container_number) or {}
    #             gate_out_line = gate_out_map.get(container_number) or {}
    #             discharge_line = discharge_map.get(container_number) or {}
    #             equipment_line = equipment_map.get(container_number) or {}
    #
    #             container_vals = {
    #                 "portbase_release_valid_until": self.parse_portbase_datetime(
    #                     release_line.get("releaseValidUntilDateTime")
    #                 ) or False,
    #                 "portbase_gate_out_time": self.parse_portbase_datetime(
    #                     gate_out_line.get("gateOut")
    #                 ) or False,
    #                 "portbase_inspection_status": inspection_map.get(container_number)
    #                 or inspection_map.get("__global__")
    #                 or False,
    #                 "portbase_inland_operator": operator_map.get(container_number) or False,
    #                 "portbase_last_sync_time": fields.Datetime.now(),
    #                 "unloading_date": self.parse_portbase_date(
    #                     discharge_line.get("actualDischargeDateTime")
    #                 ) or False,
    #             }
    #
    #             seal_number = equipment_line.get("carrierSealNumber") or equipment_line.get("shipperSealNumber")
    #             if seal_number is not None:
    #                 container_vals["seal_number"] = seal_number or False
    #
    #             if "portbase_tracking_id" in container._fields:
    #                 container_vals["portbase_tracking_id"] = payload.get("id") or container.portbase_tracking_id or False
    #
    #             container.sudo().write(container_vals)
    #
    #         _logger.info("portbase webhook processed, bl_number=%s", bl_number)
    #         return Response("OK", status=200, content_type="text/plain;charset=utf-8")
    #
    #     except Exception as err:
    #         _logger.exception("portbase webhook error: %s", err)
    #         return Response("ERROR", status=500, content_type="text/plain;charset=utf-8")
