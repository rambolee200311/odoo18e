# -*- coding: utf-8 -*-

import logging

from odoo import http
from odoo.http import request
from odoo.addons.worlddepot.controllers.api_logs import api_logger
from odoo.addons.worlddepot.controllers.validator_token import validate_token

from .common import SunriseApiError, SunriseControllerMixin

_logger = logging.getLogger(__name__)


class SunriseOutboundController(http.Controller, SunriseControllerMixin):
    @http.route("/world_depot/sunrise/api/outbound/create", type="json", auth="none", methods=["POST"], csrf=False)
    @validate_token
    @api_logger
    def create_outbound_order(self, **params):
        try:
            with request.env.cr.savepoint():
                data = self.get_request_data()
                project = self.get_api_project()
                order_type = self.get_required_text(data, "type")
                self.validate_order_type(order_type, "outbound")
                products = data.get("products")
                cwarehouseid = self.get_required_text(data, "cwarehouseid")
                vsourcebillcode = self.get_required_text(data, "vsourcebillcode")
                ccustomerid = self.get_required_text(data, "ccustomerid")
                u8c_delivery_method = self.get_required_text(data, "u8c_delivery_method").lower()
                if u8c_delivery_method not in ("pickup", "wd"):
                    raise SunriseApiError("4001", "u8c_delivery_method must be pickup or wd.")
                delivery_method = self.get_delivery_method(data)
                if not delivery_method and u8c_delivery_method == "pickup":
                    delivery_method = "pickup"
                if not isinstance(products, list) or not products:
                    raise SunriseApiError("4001", "products must be a non-empty array.")
                if not all(isinstance(line_data, dict) for line_data in products):
                    raise SunriseApiError("4001", "Each products item must be one JSON object.")
                inbound_cntr_no = [
                    self.get_optional_text(line_data, "inbound_cntr_no")
                    for line_data in products
                ]
                # if any(inbound_cntr_no) and not all(inbound_cntr_no):
                #     raise SunriseApiError(
                #         "4001",
                #         "inbound_vsourcebillcode must be provided for every products item or omitted from all items.",
                #     )

                reference = self.get_required_text(data, "reference")
                existing_order = request.env["world.depot.outbound.order"].sudo().search([
                    ("project", "=", project.id),
                    ("reference", "=", reference),
                    ("state", "!=", "cancel"),
                ], limit=1)
                if existing_order:
                    raise SunriseApiError("2001", 'Reference "%s" already exists for this project.' % reference)

                product_commands = []
                pallet_de_palletize_map = {}
                stock_checks = {}
                for index, line_data in enumerate(products, start=1):
                    parsed_line = self.prepare_outbound_product_line(line_data, index, project, vsourcebillcode)
                    sunrise_pallet_no = parsed_line["sunrise_pallet_no"]
                    de_palletize = parsed_line["product_vals"]["de_palletize"]
                    if sunrise_pallet_no in pallet_de_palletize_map and pallet_de_palletize_map[sunrise_pallet_no] != de_palletize:
                        raise SunriseApiError("4001", 'Pallet "%s" cannot mix de_palletize=N and de_palletize=Y.' % sunrise_pallet_no)
                    pallet_de_palletize_map[sunrise_pallet_no] = de_palletize

                    stock_check = parsed_line["stock_check"]
                    stock_check_key = (
                        stock_check["package"].id,
                        stock_check["product"].id,
                        stock_check["lot_name"],
                    )
                    if stock_check_key not in stock_checks:
                        stock_checks[stock_check_key] = {
                            "package": stock_check["package"],
                            "product": stock_check["product"],
                            "lot_name": stock_check["lot_name"],
                            "quantity": 0,
                        }
                    stock_checks[stock_check_key]["quantity"] += stock_check["quantity"]
                    product_commands.append((0, 0, parsed_line["product_vals"]))

                for stock_check in stock_checks.values():
                    self.check_package_stock(
                        stock_check["package"],
                        stock_check["product"],
                        stock_check["quantity"],
                        stock_check["lot_name"] or None,
                    )

                country = self.get_country(data)
                partner = self.get_partner(data, country)
                order_vals = {
                    "type": order_type,
                    "date": self.get_date_value(data, "date", required=True),
                    "p_date": self.get_date_value(data, "p_date", required=False),
                    "reference": reference,
                    "remark": self.get_optional_text(data, "remark"),
                    "project": project.id,
                    "cwarehouseid": cwarehouseid,
                    "vsourcebillcode": vsourcebillcode,
                    "ccustomerid": ccustomerid,
                    "u8c_delivery_method": u8c_delivery_method,
                    #"warehouse": project.warehouse.id if project.warehouse else False,
                    #"pick_type": project.pick_operation_type.id if project.pick_operation_type else False,
                    "creation_source": "api",
                    "delivery_method": delivery_method,
                    "load_ref": self.get_required_text(data, "load_ref"),
                    "unload_company": partner.id,
                    "delivery_street": self.get_required_text(data, "street"),
                    "delivery_zip": self.get_optional_text(data, "zip"),
                    "delivery_city": self.get_optional_text(data, "city"),
                    "delivery_country_id": country.id if country else False,
                    "delivery_phone": self.get_required_text(data, "phone"),
                    "delivery_mobile": self.get_optional_text(data, "mobile"),
                    "time_slot": self.get_optional_text(data, "time_slot"),
                    "outbound_order_product_ids": product_commands,
                }
                if "is_bonded" in request.env["world.depot.outbound.order"]._fields:
                    order_vals["is_bonded"] = False
                order = request.env["world.depot.outbound.order"].create(order_vals)
                return self.success_response(order)
        except SunriseApiError as error:
            return self.error_response(error.code, error.message)
        except Exception as error:
            _logger.exception("Unexpected Sunrise outbound create error: %s", error)
            return self.error_response("5000", str(error))

    @http.route("/world_depot/sunrise/api/outbound/cancel", type="json", auth="none", methods=["POST"], csrf=False)
    @validate_token
    @api_logger
    def cancel_outbound_order(self, **params):
        try:
            data = self.get_request_data()
            project = self.get_api_project()
            reference = self.get_required_text(data, "reference")
            order = request.env["world.depot.outbound.order"].sudo().search([
                ("project", "=", project.id),
                ("reference", "=", reference),
                ("state", "!=", "cancel"),
            ], order="id desc", limit=1)
            if not order:
                raise SunriseApiError("2002", 'Outbound order "%s" was not found.' % reference)
            if order.state != "new":
                raise SunriseApiError("2003", 'Only new outbound order "%s" can be cancelled.' % reference)
            order.action_cancel()
            return self.success_response(order)
        except SunriseApiError as error:
            return self.error_response(error.code, error.message)
        except Exception as error:
            _logger.exception("Unexpected Sunrise outbound cancel error: %s", error)
            return self.error_response("5000", str(error))

    def prepare_outbound_product_line(self, line_data, row_number, project, order_vsourcebillcode):
        product_code = self.get_required_text(line_data, "product", row_number)
        product_ean = self.get_optional_text(line_data, "product_ean")
        pallet_no = self.get_required_text(line_data, "pallet_no", row_number)
        de_palletize = self.get_optional_text(line_data, "de_palletize").upper() or "Y"
        if de_palletize not in ("N", "Y"):
            raise SunriseApiError("4001", self.format_field_error("de_palletize", "must be N or Y", row_number))
        cprojectid = self.get_required_text(line_data, "cprojectid", row_number)
        vsourcebillcode = self.get_required_text(line_data, "vsourcebillcode", row_number)
        if vsourcebillcode != order_vsourcebillcode:
            raise SunriseApiError(
                "4001",
                self.format_field_error(
                    "vsourcebillcode",
                    'must equal order vsourcebillcode "%s"' % order_vsourcebillcode,
                    row_number,
                ),
            )
        vsourcerowno = self.get_required_text(line_data, "vsourcerowno", row_number)
        cspaceid = self.get_required_text(line_data, "cspaceid", row_number)
        castunitid = self.get_required_text(line_data, "castunitid", row_number)
        u8_aux_uom_name = self.get_required_text(line_data, "u8_aux_uom_name", row_number)
        box_type, box_qty, box_in_qty, ninnum, u8_aux_qty, u8_conversion_rate = self.validate_box_values(line_data, row_number)
        is_lot, lot_name = self.validate_lot_values(line_data, row_number)
        product = self.get_sunrise_product_variant(product_code, box_type, box_in_qty, project)
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
        inbound_cntr_no = self.get_optional_text(line_data, "inbound_cntr_no")
        package = self.find_outbound_package(
            inbound_cntr_no,
            pallet_no,
            product,
            lot_name if is_lot == "Y" else "",
            project,
            row_number,
        )
        sunrise_pallet_no = package.name
        return {
            "sunrise_pallet_no": sunrise_pallet_no,
            "stock_check": {
                "package": package,
                "product": product,
                "lot_name": lot_name if is_lot == "Y" else "",
                "quantity": box_qty,
            },
            "product_vals": {
                "product_id": product.id,
                "product_ean": product_ean,
                "pallet_no": pallet_no,
                "sunrise_pallet_no": sunrise_pallet_no,
                "pallets": 1,
                "quantity": box_qty,
                "remark": self.get_optional_text(line_data, "remark"),
                "creation_source": "api",
                "de_palletize": de_palletize,
                "cprojectid": cprojectid,
                "ndiscounttaxtype": self.get_optional_text(line_data, "ndiscounttaxtype"),
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

    def find_outbound_package(self, inbound_cntr_no, pallet_no, product, lot_name, project, row_number):
        inbound_pallet_model = request.env["world.depot.inbound.order.product"].sudo()
        package_model = request.env["stock.quant.package"].sudo()

        if inbound_cntr_no:
            sunrise_pallet_no = self.get_sunrise_pallet_no(inbound_cntr_no, pallet_no)
            inbound_pallet = inbound_pallet_model.search([
                ("sunrise_pallet_no", "=", sunrise_pallet_no),
                ("pallet_no", "=", pallet_no),
                ("inbound_order_id.project", "=", project.id),
                ("inbound_order_id.state", "!=", "cancel"),
            ], limit=1)
            if not inbound_pallet:
                raise SunriseApiError(
                    "3004",
                    self.format_field_error(
                        "inbound_cntr_no",
                        '"%s" and pallet_no "%s" did not match an inbound pallet in this project'
                        % (inbound_cntr_no, pallet_no),
                        row_number,
                    ),
                )
            return self.find_package_by_sunrise_pallet_no(sunrise_pallet_no)

        inbound_pallets = inbound_pallet_model.search([
            ("pallet_no", "=", pallet_no),
            ("sunrise_pallet_no", "!=", False),
            ("inbound_order_id.project", "=", project.id),
            ("inbound_order_id.state", "!=", "cancel"),
        ])
        sunrise_pallet_numbers = inbound_pallets.mapped("sunrise_pallet_no")
        if not sunrise_pallet_numbers:
            raise SunriseApiError(
                "3004",
                self.format_field_error(
                    "pallet_no",
                    '"%s" has no inbound pallet mapping for this project' % pallet_no,
                    row_number,
                ),
            )

        packages = package_model.search([
            "|",
            ("barcode", "in", sunrise_pallet_numbers),
            ("name", "in", sunrise_pallet_numbers),
        ])
        if not packages:
            raise SunriseApiError(
                "3004",
                self.format_field_error(
                    "pallet_no",
                    '"%s" has no stock package' % pallet_no,
                    row_number,
                ),
            )

        quant_domain = [
            ("package_id", "in", packages.ids),
            ("product_id", "=", product.id),
            ("location_id.usage", "=", "internal"),
        ]
        if lot_name:
            lot = request.env["stock.lot"].sudo().search([
                ("product_id", "=", product.id),
                ("name", "=", lot_name),
            ], limit=1)
            if not lot:
                raise SunriseApiError(
                    "3003",
                    self.format_field_error("lot_name", '"%s" has no stock for this product' % lot_name, row_number),
                )
            quant_domain.append(("lot_id", "=", lot.id))

        quants = request.env["stock.quant"].sudo().search(quant_domain)
        available_by_package = {}
        for quant in quants:
            available_by_package.setdefault(quant.package_id.id, 0)
            available_by_package[quant.package_id.id] += quant.quantity - quant.reserved_quantity
        candidate_packages = packages.filtered(lambda package: available_by_package.get(package.id, 0) > 0)

        if not candidate_packages:
            raise SunriseApiError(
                "3003",
                self.format_field_error(
                    "pallet_no",
                    '"%s" has no available stock for product "%s" and lot "%s"'
                    % (pallet_no, product.display_name, lot_name or ""),
                    row_number,
                ),
            )
        if len(candidate_packages) > 1:
            raise SunriseApiError(
                "3004",
                self.format_field_error(
                    "pallet_no",
                    '"%s" matched multiple stock packages; inbound_cntr_no is required' % pallet_no,
                    row_number,
                ),
            )
        return candidate_packages

    def get_delivery_method(self, data):
        delivery_method = self.get_optional_text(data, "delivery_method")
        if not delivery_method:
            return False
        if delivery_method not in ("truck", "pickup", "parcel"):
            raise SunriseApiError("4001", "delivery_method must be truck, pickup, or parcel.")
        return delivery_method

    def get_partner(self, data, country=False):
        partner_name = self.get_required_text(data, "unload_company")
        partner = request.env["res.partner"].sudo().search([("name", "=", partner_name)], limit=1)
        if partner:
            return partner
        return request.env["res.partner"].create({
            "name": partner_name,
            "street": self.get_required_text(data, "street"),
            "zip": self.get_optional_text(data, "zip"),
            "city": self.get_optional_text(data, "city"),
            "country_id": country.id if country else False,
            "phone": self.get_required_text(data, "phone"),
            "mobile": self.get_optional_text(data, "mobile"),
        })

    def get_country(self, data):
        country_name = self.get_optional_text(data, "country")
        if not country_name:
            return request.env["res.country"].browse()
        country = request.env["res.country"].sudo().search([
            "|",
            ("name", "=", country_name),
            ("code", "=", country_name),
        ], limit=1)
        if not country:
            raise SunriseApiError("4001", 'Country "%s" was not found.' % country_name)
        return country
