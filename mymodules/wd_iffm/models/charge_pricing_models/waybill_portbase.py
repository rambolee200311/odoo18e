import logging
import time
from datetime import datetime, timezone

import requests
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class WaybillPortbaseInherit(models.Model):
    _inherit = "world.depot.waybill"
    customs_status = fields.Char(string="Customs Status", readonly=True, copy=False, index=True,tracking=True)
    portbase_tracking_id = fields.Char(string="Portbase Tracking Id", readonly=True, copy=False, index=True)
    portbase_visit_status = fields.Char(string="Portbase Visit Status", readonly=True, copy=False, index=True,tracking=True)
    portbase_last_sync_time = fields.Datetime(string="Portbase Last Sync Time", readonly=True, copy=False,tracking=True)
    portbase_sync_message = fields.Char(string="Portbase Sync Message", readonly=True, copy=False,tracking=True)

    @api.model
    def get_portbase_config(self, env_param):
        return {
            "track_requests_url": env_param.get_param("portbase-track-requests"),
            "tracked_bls_url": env_param.get_param("portbase-tracked-bls"),
            "access_key_id": env_param.get_param("portbase-access-key-id"),
            "secret_access_key": env_param.get_param("portbase-secret-access-key"),
            "access_key_id_wde": env_param.get_param("portbase-access-key-id_wde"),
            "secret_access_key_wde": env_param.get_param("portbase-secret-access-key_wde"),
            "portbase_webhook_url": env_param.get_param("portbase_webhook_url"),
        }

    @api.model
    def check_portbase_config(self, config):
        missing = []
        if not config.get("track_requests_url"):
            missing.append("portbase-track-requests")
        if not config.get("tracked_bls_url"):
            missing.append("portbase-tracked-bls")
        has_primary = bool(config.get("access_key_id") and config.get("secret_access_key"))
        has_secondary = bool(config.get("access_key_id_wde") and config.get("secret_access_key_wde"))
        if not has_primary and not has_secondary:
            missing.append("portbase-access-key-id/portbase-secret-access-key")
        if missing:
            raise UserError(_("Portbase config missing: %s") % ", ".join(missing))

    @api.model
    def get_portbase_headers_list(self, config):
        headers_list = []
        if config.get("access_key_id") and config.get("secret_access_key"):
            headers_list.append({
                "portbase-access-key-id": config["access_key_id"],
                "portbase-secret-access-key": config["secret_access_key"],
                "Content-Type": "application/json",
            })
        if config.get("access_key_id_wde") and config.get("secret_access_key_wde"):
            headers_list.append({
                "portbase-access-key-id": config["access_key_id_wde"],
                "portbase-secret-access-key": config["secret_access_key_wde"],
                "Content-Type": "application/json",
            })
        return headers_list

    @api.model
    def request_portbase(self, url, method="post", headers=None, payload=None, timeout_seconds=20, max_retries=3):
        delay_seconds = 1
        for attempt in range(max_retries):
            try:
                if method == "post":
                    response = requests.post(url, headers=headers, json=payload, timeout=timeout_seconds)
                else:
                    response = requests.get(url, headers=headers, timeout=timeout_seconds)
                if response.status_code == 200:
                    return response.json()
                _logger.warning("portbase request status=%s url=%s attempt=%s", response.status_code, url, attempt + 1)
            except Exception as err:
                _logger.warning("portbase request error=%s url=%s attempt=%s", err, url, attempt + 1)
            if attempt < max_retries - 1:
                time.sleep(delay_seconds)
                delay_seconds = delay_seconds * 2
        return False

    @api.model
    def subscribe_portbase_tracking(self, config, bl_number, container_number,WEBHOOK_URL):
        payload = {"trackRequests": [{"blNumber": bl_number, "transportEquipmentNumber": container_number,}],"webhookUrl":WEBHOOK_URL}
        for headers in self.get_portbase_headers_list(config):
            result = self.request_portbase(config["track_requests_url"], method="post", headers=headers,
                                           payload=payload)
            if not result:
                continue
            for line in (result.get("trackedBLs") or []):
                tracking_id = line.get("id")
                if tracking_id:
                    return tracking_id
            for line in (result.get("notTrackedBLs") or []):
                tracking_id = line.get("id")
                if tracking_id:
                   raise UserError(_("tracking id not found"))
        return False

    @api.model
    def fetch_portbase_tracked_item(self, config, tracking_id):
        detail_url = "%s?id=%s" % (config["tracked_bls_url"], tracking_id)
        for headers in self.get_portbase_headers_list(config):
            result = self.request_portbase(detail_url, method="get", headers=headers, payload=None)
            if isinstance(result, list) and result:
                return result[0]
            if isinstance(result, dict) and result.get("billOfLading"):
                return result
        return False

    @api.model
    def fetch_portbase_by_bl_and_container(self, bl_number, container_number):
        env_param = self.env["ir.config_parameter"].sudo()
        config = self.get_portbase_config(env_param)
        self.check_portbase_config(config)
        WEBHOOK_URL = config["portbase_webhook_url"]

        tracking_id = self.subscribe_portbase_tracking(config, bl_number, container_number,WEBHOOK_URL)
        if not tracking_id:
            raise UserError(_("Subscribe tracking id failed, bl=%s cntr=%s") % (bl_number, container_number))

        tracked_item = self.fetch_portbase_tracked_item(config, tracking_id)
        if not tracked_item:
            raise UserError(_("Tracked detail not ready, tracking id=%s") % tracking_id)

        return tracked_item, tracking_id

    @api.model
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
        return dt_value

    @api.model
    def parse_portbase_date(self, value):
        dt_value = self.parse_portbase_datetime(value)
        return dt_value.date() if dt_value else False

    @api.model
    def to_float_value(self, value):
        try:
            return float(value or 0.0)
        except Exception:
            return 0.0

    @api.model
    def to_int_value(self, value):
        try:
            return int(float(value or 0))
        except Exception:
            return 0

    @api.model
    def map_container_type(self, size_type_code):
        code = (size_type_code or "").upper()
        if code.startswith("20"):
            return "20GP"
        if code.startswith("45"):
            return "45HQ"
        if code.startswith("40") and ("H" in code or "HC" in code or "HQ" in code):
            return "40HQ"
        if code.startswith("40"):
            return "40GP"
        return "40GP"

    def get_or_create_port_node(self, node_name, node_type, country_id, terminal_code=False, parent_id=False):
        env_port_node = self.env["world.depot.port.node"]
        if not node_name:
            return False

        domain = [("name", "=", node_name), ("node_type", "=", node_type)]
        if node_type == "terminal" and parent_id:
            domain.append(("parent_id", "=", parent_id))

        node_ids = env_port_node.sudo().search(domain, limit=1).ids
        if node_ids:
            return env_port_node.browse(node_ids[0])

        vals = {
            "name": node_name,
            "node_type": node_type,
            "country_id": country_id,
            "terminal_code": terminal_code or node_name,
        }
        if node_type == "terminal" and parent_id:
            vals["parent_id"] = parent_id
        return env_port_node.create(vals)

    def get_country_id_from_un_code(self, location_un_code):
        env_country = self.env["res.country"]
        country_code = (location_un_code or "").strip().upper()[:2]
        if country_code:
            country_ids = env_country.sudo().search([("code", "=", country_code)], limit=1).ids
            if country_ids:
                return country_ids[0]
        if self.env.company.country_id:
            return self.env.company.country_id.id
        raise UserError(_("Can not resolve country from location code: %s") % (location_un_code or ""))

    @api.model
    def upsert_waybill_from_portbase(self, tracked_item, default_project_id, input_bl_number=False, tracking_id=False):
        env_waybill = self.env["world.depot.waybill"]

        bill = tracked_item.get("billOfLading") or {}
        vessel_visit = bill.get("vesselVisit") or {}
        port_visit = (vessel_visit.get("visitDeclaration") or {}).get("portVisit") or {}

        port_of_discharge = bill.get("portOfDischarge") or {}
        discharge_terminal = bill.get("dischargeTerminal") or {}
        handling_agent = bill.get("handlingAgent") or {}

        discharge_port_name = port_of_discharge.get("locationName") or False
        discharge_port_un_code = port_of_discharge.get("locationUnCode") or False
        discharge_terminal_name = discharge_terminal.get("name") or False
        discharge_terminal_code = discharge_terminal.get("code") or False

        country_id = self.get_country_id_from_un_code(discharge_port_un_code)
        port_node = self.get_or_create_port_node(
            discharge_port_name,
            "port",
            country_id,
            terminal_code=discharge_port_un_code or discharge_port_name,
        )
        terminal_node = self.get_or_create_port_node(
            discharge_terminal_name or discharge_terminal_code,
            "terminal",
            country_id,
            terminal_code=discharge_terminal_code or discharge_terminal_name,
            parent_id=port_node.id if port_node else False,
        )
        shipping_name = handling_agent.get("name") or False
        shipping = self.env["res.partner"].sudo().search([("name", "=", shipping_name)], limit=1)
        if not shipping:
            shipping_partner = self.env["res.partner"].sudo().create({
            "name": shipping_name,
            "is_shipping_line": True,
            "company_type": "company",
        })
        else:
            if not shipping.is_shipping_line:
                shipping.write({"is_shipping_line": True})
            shipping_partner = shipping

        bl_number = bill.get("blNumber") or input_bl_number
        if not bl_number:
            raise UserError(_("No bl number in tracked item"))

        waybill_vals = {
            "shipping": shipping_partner.id if shipping_partner else False,
            "port_id": port_node.id if port_node else False,
            "terminal_id": terminal_node.id if terminal_node else False,
            "voyage_no": vessel_visit.get("crn") or False,
            "eta": self.parse_portbase_date(port_visit.get("etaPort")),
            "ata": self.parse_portbase_date(port_visit.get("ataPort")),
            'is_arrived':True if port_visit.get("ataPort") else False,
            "customs_status": bill.get("customsStatus") or False,
            "portbase_tracking_id": tracking_id or False,
            "portbase_visit_status": vessel_visit.get("visitStatus") or False,
            "portbase_last_sync_time": fields.Datetime.now(),
        }

        waybill_ids = env_waybill.sudo().search([("bl_number", "=", bl_number), ("state", "!=", "cancel")], limit=1).ids
        if waybill_ids:
            waybill = env_waybill.browse(waybill_ids[0])
            waybill.write(waybill_vals)
            return waybill

        waybill_vals.update({"project": default_project_id, "bl_number": bl_number})
        return env_waybill.create(waybill_vals)

    @api.model
    def get_line_map_by_container(self, lines):
        line_map = {}
        for line in (lines or []):
            equipment_number = line.get("equipmentNumber")
            if equipment_number:
                line_map[equipment_number] = line
        return line_map

    @api.model
    def get_inspection_status_map(self, lines):
        status_map = {}
        for line in (lines or []):
            status = line.get("status")
            equipment_numbers = line.get("equipmentNumbers") or []
            if not equipment_numbers and status:
                status_map["__global__"] = status
                continue
            for equipment_number in equipment_numbers:
                if equipment_number and status:
                    status_map[equipment_number] = status
        return status_map

    @api.model
    def get_inland_operator_map(self, lines):
        operator_map = {}
        for line in (lines or []):
            equipment_number = line.get("equipmentNumber")
            operator_name = line.get("inlandOperatorFullName")
            if equipment_number:
                operator_map[equipment_number] = operator_name
        return operator_map

    @api.model
    def sync_waybill_full_containers_from_portbase(self, waybill, tracked_item, tracking_id):
        env_container = self.env["world.depot.waybill.container"]
        env_packing = self.env["world.depot.waybill.packing.list"]

        bill = tracked_item.get("billOfLading") or {}
        equipment_lines = bill.get("transportEquipments") or []
        if not equipment_lines:
            raise UserError(_("No transportEquipments in tracked item"))

        remote_numbers = {line.get("equipmentNumber") for line in equipment_lines if line.get("equipmentNumber")}
        if not remote_numbers:
            raise UserError(_("No equipmentNumber in tracked item"))
        #卸船报告
        discharge_map = self.get_line_map_by_container(bill.get("dischargeReports"))
        #放行内容
        release_map = self.get_line_map_by_container(bill.get("commercialReleases"))
        #这个箱在内陆 / 后续节点上的状态
        hinterland_map = self.get_line_map_by_container(bill.get("hinterlandTerminalData"))
        #查验记录
        inspection_map = self.get_inspection_status_map(bill.get("inspectionItems"))
        #内陆承运人
        operator_map = self.get_inland_operator_map(tracked_item.get("nominatedInlandOperators"))

        local_container_ids = env_container.sudo().search([("waybill_id", "=", waybill.id)]).ids
        local_containers = env_container.browse(local_container_ids)
        local_map = {rec.container_number: rec for rec in local_containers}

        for equipment in equipment_lines:
            container_number = equipment.get("equipmentNumber")
            if not container_number:
                continue

            discharge = discharge_map.get(container_number) or {}
            release = release_map.get(container_number) or {}
            hinterland = hinterland_map.get(container_number) or {}

            release_dt = self.parse_portbase_datetime(release.get("releaseValidUntilDateTime"))
            gate_out_dt = self.parse_portbase_datetime(hinterland.get("gateOut"))
            discharge_dt = self.parse_portbase_datetime(discharge.get("actualDischargeDateTime"))

            container_vals = {
                "waybill_id": waybill.id,
                "container_number": container_number,
                "container_type": self.map_container_type((equipment.get("sizeType") or {}).get("code")),
                "weight": self.to_float_value(equipment.get("tareWeight")),
                "seal_number": equipment.get("carrierSealNumber") or equipment.get("shipperSealNumber") or False,
                "portbase_tracking_id": tracking_id,
                "portbase_release_valid_until": release_dt or False,
                "portbase_gate_out_time": gate_out_dt or False,
                "portbase_inspection_status": inspection_map.get(container_number) or inspection_map.get(
                    "__global__") or False,
                "portbase_inland_operator": operator_map.get(container_number) or False,
                "portbase_last_sync_time": fields.Datetime.now(),
                "unloading_date": discharge_dt.date() if discharge_dt else False,
            }

            container = local_map.get(container_number)
            if container:
                container.write(container_vals)
            else:
                container = env_container.create(container_vals)

            old_pack_ids = env_packing.sudo().search([("container_id", "=", container.id)]).ids
            if old_pack_ids:
                env_packing.browse(old_pack_ids).unlink()

            commands = self.build_container_packing_commands(bill, container, remote_numbers)
            if commands:
                container.write({"packing_list_ids": commands})

        missing_containers = local_containers.filtered(lambda rec: rec.container_number not in remote_numbers)
        if missing_containers:
            missing_ids = missing_containers.ids
            missing_pack_ids = env_packing.sudo().search([("container_id", "in", missing_ids)]).ids
            if missing_pack_ids:
                env_packing.browse(missing_pack_ids).unlink()
            missing_containers.unlink()

        waybill.write({
            "portbase_tracking_id": tracking_id,
            "portbase_last_sync_time": fields.Datetime.now(),
            "portbase_sync_message": _("Synced by tracking id %s") % tracking_id,
        })

    @api.model
    def build_container_packing_commands(self, bill, container, remote_numbers):
        commands = []
        goods_items = bill.get("goodsItems") or []

        for goods in goods_items:
            commodity = goods.get("commodity") or {}
            dangerous = goods.get("dangerousGoods") or {}
            transport_lines = goods.get("goodsItemTransportEquipments") or []

            if transport_lines:
                for line in transport_lines:
                    equipment_number = line.get("equipmentNumber")
                    if equipment_number != container.container_number:
                        continue
                    quantity = self.to_float_value(line.get("numberOfPackages") or goods.get("numberOfOuterPackages"))
                    total_weight = self.to_float_value(line.get("grossWeight") or goods.get("grossWeight"))
                    commands.append((0, 0, {
                        "waybill_id": container.waybill_id.id,
                        "container_id": container.id,
                        "container_number": container.container_number,
                        "description": goods.get("description") or commodity.get("description") or False,
                        "adr": bool(dangerous),
                        "un_number": dangerous.get("unCode") or False,
                        "quantity": quantity,
                        "pallets": quantity,
                        "total_weight": total_weight,
                        "total_packages": self.to_int_value(
                            line.get("numberOfPackages") or goods.get("numberOfOuterPackages")),
                        "remark": ("HS:%s" % commodity.get("code")) if commodity.get("code") else False,
                    }))
                continue

            if len(remote_numbers) == 1 and container.container_number in remote_numbers:
                quantity = self.to_float_value(goods.get("numberOfOuterPackages"))
                total_weight = self.to_float_value(goods.get("grossWeight"))
                commands.append((0, 0, {
                    "waybill_id": container.waybill_id.id,
                    "container_id": container.id,
                    "container_number": container.container_number,
                    "description": goods.get("description") or commodity.get("description") or False,
                    "adr": bool(dangerous),
                    "un_number": dangerous.get("unCode") or False,
                    "quantity": quantity,
                    "pallets": quantity,
                    "total_weight": total_weight,
                    "total_packages": self.to_int_value(goods.get("numberOfOuterPackages")),
                    "remark": ("HS:%s" % commodity.get("code")) if commodity.get("code") else False,
                }))

        return commands


class WaybillContainerPortbaseInherit(models.Model):
    _inherit = "world.depot.waybill.container"

    portbase_tracking_id = fields.Char(string="Portbase Tracking Id", readonly=True, copy=False, index=True)
    portbase_release_valid_until = fields.Datetime(string="Portbase Release Valid Until", readonly=True, copy=False,tracking=True)
    portbase_gate_out_time = fields.Datetime(string="Portbase Gate Out Time", readonly=True, copy=False,tracking=True)
    portbase_inspection_status = fields.Char(string="Portbase Inspection Status", readonly=True, copy=False,tracking=True)
    portbase_inland_operator = fields.Char(string="Portbase Inland Operator", readonly=True, copy=False,tracking=True)
    portbase_last_sync_time = fields.Datetime(string="Portbase Last Sync Time", readonly=True, copy=False,tracking=True)
