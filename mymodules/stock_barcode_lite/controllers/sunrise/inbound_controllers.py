# -*- coding: utf-8 -*-

import logging
from odoo.exceptions import UserError, ValidationError
from odoo import http
from odoo.http import request
from odoo.addons.worlddepot.controllers.api_logs import api_logger
from odoo.addons.worlddepot.controllers.validator_token import validate_token

from .common import SunriseApiError, SunriseControllerMixin

_logger = logging.getLogger(__name__)


class SunriseInboundController(http.Controller, SunriseControllerMixin):
    @http.route("/world_depot/sunrise/api/inbound/create", type="json", auth="none", methods=["POST"], csrf=False)
    @validate_token
    @api_logger
    def create_inbound_order(self, **params):
        try:
            with request.env.cr.savepoint():
                data = self.get_request_data()
                project = self.get_api_project()
                order_type = self.get_required_text(data, "type")
                self.validate_order_type(order_type, "inbound")
                products = data.get("products")
                cntr_no = self.get_required_text(data, "cntr_no")
                cwarehouseid = self.get_required_text(data, "cwarehouseid")
                if order_type == "service":
                    source_sale_delivery_reference = self.get_required_text(data, "source_sale_delivery_reference")
                else:
                    source_sale_delivery_reference = self.get_optional_text(data, "source_sale_delivery_reference")
                if not isinstance(products, list) or not products:
                    raise SunriseApiError("4001", "products must be a non-empty array.")

                reference = self.get_required_text(data, "reference")
                existing_order = request.env["world.depot.inbound.order"].sudo().search([
                    ("project", "=", project.id),
                    ("reference", "=", reference),
                    ("state", "!=", "cancel"),
                ], limit=1)
                if existing_order:
                    raise SunriseApiError("2001", 'Reference "%s" already exists for this project.' % reference)

                parsed_lines = []
                vsourcebillcodes = set()
                raw_pallet_numbers = set()
                sunrise_pallet_numbers = set()
                for index, line_data in enumerate(products, start=1):
                    parsed_line = self.prepare_inbound_product_line(line_data, index, project, cntr_no)
                    parsed_lines.append(parsed_line)
                    vsourcebillcodes.add(parsed_line["vsourcebillcode"])
                    raw_pallet_numbers.add(parsed_line["pallet_no"])
                    sunrise_pallet_numbers.add(parsed_line["sunrise_pallet_no"])
                if len(vsourcebillcodes) != 1:
                    raise SunriseApiError("4001", "All product lines must use the same vsourcebillcode.")
                vsourcebillcode = list(vsourcebillcodes)[0]
                #传过来的托
                existing_pallet = request.env["world.depot.inbound.order.product"].sudo().search([
                    ("pallet_no", "in", list(raw_pallet_numbers)),
                    ("inbound_order_id.project", "=", project.id),
                    ("inbound_order_id.state", "!=", "cancel"),
                ], limit=1)

                if existing_pallet:
                    raise SunriseApiError(
                        "3004",
                        'Pallet No "%s" already exists in inbound order "%s" for this project.'
                        % (
                            existing_pallet.pallet_no,
                            existing_pallet.inbound_order_id.billno
                            or existing_pallet.inbound_order_id.reference,
                        ),
                    )
                #wms托
                existing_pallet = request.env["world.depot.inbound.order.product"].sudo().search([
                    ("sunrise_pallet_no", "in", list(sunrise_pallet_numbers)),
                    ("inbound_order_id.project", "=", project.id),
                    ("inbound_order_id.state", "!=", "cancel"),
                    ("inbound_order_id.type", "=", "inbound"),
                ], limit=1)
                if existing_pallet:
                    raise SunriseApiError(
                        "3004",
                        'This Sunrise Pallet "%s" already exists in inbound order "%s".'
                        % (existing_pallet.sunrise_pallet_no, existing_pallet.inbound_order_id.billno or existing_pallet.inbound_order_id.reference),
                    )

                pallet_data = {}
                for parsed_line in parsed_lines:
                    pallet_no = parsed_line["pallet_no"]
                    if pallet_no not in pallet_data:
                        pallet_data[pallet_no] = {
                            "pallet_no": pallet_no,
                            "sunrise_pallet_no": parsed_line["sunrise_pallet_no"],
                            "pallets": 1,
                            "creation_source": "api",
                            "inbound_order_product_pallet_ids": [],
                        }
                    pallet_data[pallet_no]["inbound_order_product_pallet_ids"].append((0, 0, parsed_line["product_vals"]))

                order_vals = {
                    "type": order_type,
                    "is_bonded":False,
                    "date": self.get_date_value(data, "date", required=True),
                    "a_date": self.get_date_value(data, "a_date", required=True),
                    "reference": reference,
                    "bl_no": self.get_optional_text(data, "bl_no"),
                    "cntr_no": self.get_optional_text(data, "cntr_no"),
                    "cwarehouseid": cwarehouseid,
                    "source_sale_delivery_reference": source_sale_delivery_reference,
                    "vsourcebillcode": vsourcebillcode,
                    "remark": self.get_optional_text(data, "remark"),
                    "project": project.id,
                    # "warehouse": project.warehouse.id if project.warehouse else False,
                    # "pick_type": project.receipt_operation_type.id if project.receipt_operation_type else False,
                    "creation_source": "api",
                    "inbound_order_product_ids": [(0, 0, values) for values in pallet_data.values()],
                }
                order = request.env["world.depot.inbound.order"].create(order_vals)
                return self.success_response(order)
        except SunriseApiError as error:
            return self.error_response(error.code, error.message)
        except Exception as error:
            _logger.exception("Unexpected Sunrise inbound create error: %s", error)
            return self.error_response("5000", str(error))

    @http.route("/world_depot/sunrise/api/inbound/cancel", type="json", auth="none", methods=["POST"], csrf=False)
    @validate_token
    @api_logger
    def cancel_inbound_order(self, **params):
        try:
            data = self.get_request_data()
            project = self.get_api_project()
            reference = self.get_required_text(data, "reference")
            order = request.env["world.depot.inbound.order"].sudo().search([
                ("project", "=", project.id),
                ("reference", "=", reference),
                ("state", "!=", "cancel"),
            ], order="id desc", limit=1)
            if not order:
                raise SunriseApiError("2002", 'Inbound order "%s" was not found.' % reference)
            if order.state == "new":
                if order.stock_picking_id.state =='done':
                    raise UserError ("You cannot cancel a done picking")
            order.action_cancel()
            return self.success_response(order)
        except SunriseApiError as error:
            return self.error_response(error.code, error.message)
        except Exception as error:
            _logger.exception("Unexpected Sunrise inbound cancel error: %s", error)
            return self.error_response("5000", str(error))

    def prepare_inbound_product_line(self, line_data, row_number, project,cntr_no):
        product_code = self.get_required_text(line_data, "product", row_number)
        product_ean = self.get_optional_text(line_data, "product_ean")
        pallet_no = self.get_required_text(line_data, "pallet_no", row_number)
        cprojectid = self.get_required_text(line_data, "cprojectid", row_number)
        ndiscounttaxtype = self.get_required_text(line_data, "ndiscounttaxtype", row_number)
        vsourcebillcode = self.get_required_text(line_data, "vsourcebillcode", row_number)
        vsourcerowno = self.get_required_text(line_data, "vsourcerowno", row_number)
        castunitid = self.get_required_text(line_data, "castunitid", row_number)
        cspaceid = self.get_required_text(line_data, "cspaceid", row_number)
        u8_aux_uom_name = self.get_required_text(line_data, "u8_aux_uom_name", row_number)
        box_type, box_qty, box_in_qty, ninnum, u8_aux_qty, u8_conversion_rate = self.validate_box_values(line_data, row_number)
        is_lot, lot_name = self.validate_lot_values(line_data, row_number)
        product = self.get_sunrise_product_variant(product_code, box_type, box_in_qty, project, auto_create_variant=True)
        if product.tracking == "lot" and is_lot != "Y":
            raise SunriseApiError(
                "4001",
                self.format_field_error("is_lot", "must be Y for lot-tracked product", row_number),
            )

        if product.tracking != "lot" and is_lot != "N":
            raise SunriseApiError(
                "4001",
                self.format_field_error("is_lot", "must be N for non-lot-tracked product", row_number),
            )
        sunrise_pallet_no = self.get_sunrise_pallet_no(cntr_no, pallet_no)
        return {
            "pallet_no": pallet_no,
            "sunrise_pallet_no": sunrise_pallet_no,
            "vsourcebillcode": vsourcebillcode,
            "product_vals": {
                "product_id": product.id,
                "product_ean": product_ean,
                "quantity": box_qty,
                "remark": self.get_optional_text(line_data, "remark"),
                "creation_source": "api",
                "cprojectid": cprojectid,
                "ndiscounttaxtype": ndiscounttaxtype,
                "vsourcebillcode": vsourcebillcode,
                "vsourcerowno": vsourcerowno,
                "cspaceid": cspaceid,
                "box_type": box_type,
                "box_qty": box_qty,
                "box_in_qty": box_in_qty,
                "ninnum": ninnum,
                "u8_aux_qty": u8_aux_qty,
                "u8_conversion_rate": u8_conversion_rate,
                "castunitid": castunitid,
                "u8_aux_uom_name": u8_aux_uom_name,
                "is_lot": is_lot,
                "lot_name": lot_name,
                "m_date": self.get_date_value(line_data, "m_date", row_number=row_number),
                "e_date": self.get_date_value(line_data, "e_date", row_number=row_number),
            },
        }
