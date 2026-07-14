# -*- coding: utf-8 -*-

import json
import logging
import math
import re
import uuid
from datetime import datetime

from odoo.http import request

_logger = logging.getLogger(__name__)


class SunriseApiError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class SunriseControllerMixin:
    supported_order_types = ("inbound", "outbound", "service", "transfer")

    def get_request_data(self):
        raw_data = request.httprequest.data.decode("utf-8") if request.httprequest.data else ""
        if not raw_data and getattr(request, "jsonrequest", None):
            data = request.jsonrequest
        else:
            try:
                data = json.loads(raw_data or "{}")
            except json.JSONDecodeError as error:
                raise SunriseApiError("4001", "Invalid JSON request body: %s" % error) from error
        if not isinstance(data, dict):
            raise SunriseApiError("4001", "Request body must be one JSON object.")
        return data

    def success_response(self, order):
        return {
            "success": True,
            "data": {
                "billno": order.billno,
                "id": order.id,
                "state": order.state,
            },
            "code": "200",
        }

    def error_response(self, code, message):
        return {
            "success": False,
            "msg": message,
            "code": code,
        }

    def get_api_project(self):
        api_user = getattr(request, "api_user", False)
        project = api_user.project if api_user and api_user.project else False
        if not project:
            raise SunriseApiError("4001", "API user is not bound to a project.")
        return project

    def get_required_text(self, data, field_name, row_number=None):
        value = data.get(field_name)
        if value is None or str(value).strip() == "":
            raise SunriseApiError("4001", self.format_field_error(field_name, "is required", row_number))
        return str(value).strip()

    def get_optional_text(self, data, field_name):
        value = data.get(field_name)
        if value is None:
            return ""
        return str(value).strip()

    def get_date_value(self, data, field_name, required=False, row_number=None):
        value = data.get(field_name)
        if value in (None, ""):
            if required:
                raise SunriseApiError("4001", self.format_field_error(field_name, "is required", row_number))
            return False
        if not isinstance(value, str):
            raise SunriseApiError("4001", self.format_field_error(field_name, "must use YYYY-MM-DD format", row_number))
        try:
            parsed_date = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as error:
            raise SunriseApiError("4001", self.format_field_error(field_name, "must use YYYY-MM-DD format",
                                                                  row_number)) from error
        if parsed_date.strftime("%Y-%m-%d") != value:
            raise SunriseApiError("4001", self.format_field_error(field_name, "must use YYYY-MM-DD format", row_number))
        return value

    def get_positive_int(self, data, field_name, row_number=None):
        value = data.get(field_name)
        if isinstance(value, bool) or value in (None, ""):
            raise SunriseApiError("4001", self.format_field_error(field_name, "must be a positive integer", row_number))
        if isinstance(value, int):
            number = value
        elif isinstance(value, str) and value.strip().isdigit():
            number = int(value.strip())
        else:
            raise SunriseApiError("4001", self.format_field_error(field_name, "must be a positive integer", row_number))
        if number <= 0:
            raise SunriseApiError("4001", self.format_field_error(field_name, "must be a positive integer", row_number))
        return number

    def get_positive_float(self, data, field_name, row_number=None):
        value = data.get(field_name)
        if isinstance(value, bool) or value in (None, ""):
            raise SunriseApiError("4001", self.format_field_error(field_name, "must be a positive number", row_number))
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise SunriseApiError(
                "4001",
                self.format_field_error(field_name, "must be a positive number", row_number),
            ) from error
        if not math.isfinite(number) or number <= 0:
            raise SunriseApiError("4001", self.format_field_error(field_name, "must be a positive number", row_number))
        return number

    def format_field_error(self, field_name, message, row_number=None):
        if row_number:
            return "Line %s: %s %s." % (row_number, field_name, message)
        return "%s %s." % (field_name, message)

    def validate_order_type(self, order_type, expected_type):
        if order_type == "other":
            raise SunriseApiError("4001", "Order type other is not supported by the current model.")
        if expected_type == "inbound" and order_type not in ("inbound", "service", "transfer"):
            raise SunriseApiError("4001", "Inbound order type must be inbound, service, or transfer.")
        if expected_type == "outbound" and order_type not in ("outbound", "service", "transfer"):
            raise SunriseApiError("4001", "Outbound order type must be outbound, service, or transfer.")

    def validate_box_values(self, line_data, row_number=None):
        box_type = self.get_required_text(line_data, "box_type", row_number).lower()
        if box_type not in ("full", "partial"):
            raise SunriseApiError("4001", self.format_field_error("box_type", "must be full or partial", row_number))
        box_qty = self.get_positive_int(line_data, "box_qty", row_number)
        box_in_qty = self.get_positive_float(line_data, "box_in_qty", row_number)
        ninnum = self.get_positive_float(line_data, "ninnum", row_number)
        u8_aux_qty = self.get_positive_float(line_data, "u8_aux_qty", row_number)
        u8_conversion_rate = self.get_positive_float(line_data, "u8_conversion_rate", row_number)
        if not math.isclose(ninnum, box_qty * box_in_qty, rel_tol=1e-9, abs_tol=1e-6):
            raise SunriseApiError("4001",
                                  self.format_field_error("ninnum", "must equal box_qty * box_in_qty", row_number))

        if box_type == "full" and not math.isclose(box_in_qty,u8_conversion_rate,rel_tol=1e-9,abs_tol=1e-6,):
            raise SunriseApiError("4001",self.format_field_error("box_in_qty","must equal u8_conversion_rate when box_type is full",row_number,),)

        if box_type == "partial" and math.isclose(
                box_in_qty,
                u8_conversion_rate,
                rel_tol=1e-9,
                abs_tol=1e-6,
        ):
            raise SunriseApiError(
                "4001",
                self.format_field_error(
                    "box_in_qty",
                    "must not equal u8_conversion_rate when box_type is partial",
                    row_number,
                ),
            )
        return box_type, box_qty, box_in_qty, ninnum, u8_aux_qty, u8_conversion_rate

    def validate_lot_values(self, line_data, row_number=None):
        is_lot = self.get_required_text(line_data, "is_lot", row_number).upper()
        if is_lot not in ("Y", "N"):
            raise SunriseApiError("4001", self.format_field_error("is_lot", "must be Y or N", row_number))
        lot_name = self.get_optional_text(line_data, "lot_name")
        if is_lot == "Y" and not lot_name:
            raise SunriseApiError("4001",
                                  self.format_field_error("lot_name", "is required when is_lot is Y", row_number))
        return is_lot, lot_name
#拼wms托盘号
    def get_sunrise_pallet_no(self, cntr_no, pallet_no):
        return "%s-%s" % (cntr_no, pallet_no)

    def generate_sunrise_pallet_no(self, project, pallet_no):
        package_model = request.env["stock.quant.package"].sudo()
        pallet_model = request.env["world.depot.inbound.order.product"].sudo()
        project_code = re.sub(r"\s+", "", (project.name if project else "SUNRISE") or "SUNRISE").upper()
        pallet_code = re.sub(r"\s+", "", pallet_no or "").upper()
        if not pallet_code:
            raise SunriseApiError("4001", "pallet_no is required.")

        for _attempt in range(20):
            barcode = "%s-%s-%s" % (project_code, pallet_code, uuid.uuid4().hex[:6].upper())
            existing_package = package_model.search([("barcode", "=", barcode)], limit=1)
            existing_pallet = pallet_model.search([("sunrise_pallet_no", "=", barcode)], limit=1)
            if not existing_package and not existing_pallet:
                return barcode

        raise SunriseApiError("5000", 'Could not generate a unique package barcode for pallet "%s".' % pallet_no)

    def get_sunrise_package_value_name(self, box_type, box_in_qty):
        if box_type == "full":
            return "Standard Packaging"
        return "Non standard package%s" % box_in_qty

    def get_sunrise_package_variants(self, variants, value_name):
        return variants.filtered(
            lambda variant: value_name in variant.product_template_attribute_value_ids.mapped("name")
        )

    def get_sunrise_variant_default_code(self, product_code, box_type, box_in_qty):
        if box_type == "full":
            return "%s-FULL-%s" % (product_code, box_in_qty)
        return "%s-PARTIAL-%s" % (product_code, box_in_qty)

    def get_sunrise_product_variant(self, product_code, box_type, box_in_qty, project,
                                    auto_create_variant=False):
        product_model = request.env["product.product"]
        standard_products = product_model.sudo().search([
            ("barcode", "=", product_code),
        ])

        if project.category:
            standard_products = standard_products.filtered(
                lambda product: product.categ_id == project.category
            )

        if not standard_products:
            raise SunriseApiError(
                "3001",
                'Standard carton product with barcode "%s" was not found.' % product_code,
            )

        if len(standard_products) > 1:
            raise SunriseApiError(
                "3001",
                'Barcode "%s" matched multiple standard carton products.' % product_code,
            )

        standard_product = product_model.browse(standard_products[:1].id)

        # 传入产品编码对应的 barcode 就是标准箱产品。
        if box_type == "full":
            return standard_product

        template = standard_product.product_tmpl_id
        target_value_name = self.get_sunrise_package_value_name(box_type, box_in_qty)

        variants = product_model.sudo().search([
            ("product_tmpl_id", "=", template.id),
        ])
        matched_variants = self.get_sunrise_package_variants(
            variants,
            target_value_name,
        )

        # 只允许入库自动创建零箱变体。
        if not matched_variants and auto_create_variant:
            self.ensure_sunrise_package_value_on_template(
                template,
                target_value_name,
            )
            variants = product_model.sudo().search([
                ("product_tmpl_id", "=", template.id),
            ])
            matched_variants = self.get_sunrise_package_variants(
                variants,
                target_value_name,
            )

        if not matched_variants:
            raise SunriseApiError(
                "3001",
                'Product barcode "%s" has no partial variant with package value "%s".'
                % (product_code, target_value_name),
            )

        if len(matched_variants) > 1:
            raise SunriseApiError(
                "3001",
                'Product barcode "%s" has multiple partial variants with package value "%s".'
                % (product_code, target_value_name),
            )

        product = product_model.browse(matched_variants[:1].id)

        if auto_create_variant and not product.default_code:
            product.write({
                "default_code": self.get_sunrise_variant_default_code(
                    product_code,
                    box_type,
                    box_in_qty,
                ),
                "barcode": self.get_sunrise_variant_default_code(
                    product_code,
                    box_type,
                    box_in_qty,
                ),
            })

        return product

    # 建属性值
    def ensure_sunrise_package_value_on_template(self, template, value_name):
        attribute = request.env["product.attribute"].sudo().search([("name", "=", "Packaging Specifications")], limit=1)
        if not attribute:
            raise SunriseApiError("3001", 'No attribute named "Packaging Specifications" was found.')

        value = request.env["product.attribute.value"].sudo().search([
            ("attribute_id", "=", attribute.id),
            ("name", "=", value_name),
        ], limit=1)

        if not value:
            value = request.env["product.attribute.value"].create({
                "attribute_id": attribute.id,
                "name": value_name,
            })
        line_model = request.env["product.template.attribute.line"]
        line = line_model.sudo().search([
            ("product_tmpl_id", "=", template.id),
            ("attribute_id", "=", attribute.id),
        ], limit=1)
        if line:
            normal_line = line_model.browse(line.id)
            if value.id not in line.value_ids.ids:
                normal_line.write({"value_ids": [(4, value.id)]})
        else:
            line_model.create({
                "product_tmpl_id": template.id,
                "attribute_id": attribute.id,
                "value_ids": [(6, 0, [value.id])],
            })

    def is_sunrise_variant_match(self, variant, box_type, box_qty, units_per_carton):
        text = self.get_variant_match_text(variant)
        full_tokens = ("full", "standard", "standard packaging", "整箱", "标准", "標準")
        partial_tokens = ("partial", "nonstandard", "non-standard", "non standard", "零箱", "非标准", "非標準")
        has_full_type = any(token in text for token in full_tokens)
        has_partial_type = any(token in text for token in partial_tokens)
        has_box_qty = bool(re.search(r"(?<!\d)%s(?!\d)" % re.escape(str(box_qty)), text))
        if box_type == "full":
            return box_qty == units_per_carton and has_full_type and (
                        has_box_qty or len(variant.product_tmpl_id.product_variant_ids) == 1)
        return box_qty < units_per_carton and has_partial_type and has_box_qty

    def get_variant_match_text(self, variant):
        attribute_values = variant.product_template_attribute_value_ids
        parts = [
            variant.display_name or "",
            variant.name or "",
            variant.default_code or "",
            variant.barcode or "",
            variant.product_tmpl_id.name or "",
        ]
        parts.extend(attribute_values.mapped("name"))
        parts.extend(attribute_values.mapped("attribute_id.name"))
        return " ".join(parts).lower()

    def find_package_by_sunrise_pallet_no(self, sunrise_pallet_no):
        package_model = request.env["stock.quant.package"].sudo()
        packages = package_model.search([("barcode", "=", sunrise_pallet_no)])
        if not packages:
            raise SunriseApiError("3004", 'Pallet "%s" does not exist in stock package.' % sunrise_pallet_no)
        if len(packages) > 1:
            raise SunriseApiError("3004", 'Pallet "%s" matched multiple stock packages.' % sunrise_pallet_no)
        return packages

    def check_package_stock(self, package, product, quantity, lot_name=None):
        quant_model = request.env["stock.quant"].sudo()
        quant_domain = [
            ("package_id", "=", package.id),
            ("product_id", "=", product.id),
            ("location_id.usage", "=", "internal"),
        ]
        if lot_name:
            lot = request.env["stock.lot"].sudo().search([
                ("product_id", "=", product.id),
                ("name", "=", lot_name),
            ], limit=1)
            if not lot:
                raise SunriseApiError("3003",
                                      'Lot "%s" has no stock for product "%s".' % (lot_name, product.display_name))
            quant_domain.append(("lot_id", "=", lot.id))
        quants = quant_model.search(quant_domain)
        available_quantity = sum(quants.mapped("quantity")) - sum(quants.mapped("reserved_quantity"))
        if available_quantity < quantity:
            raise SunriseApiError(
                "3003",
                'Insufficient stock for product "%s" on pallet "%s": need %s, available %s.'
                % (product.display_name, package.name, quantity, available_quantity),
            )
