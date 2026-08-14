# -*- coding: utf-8 -*-

import base64
from datetime import date, datetime, time
from urllib.parse import quote

from odoo import fields
from odoo.osv import expression
from odoo.tools.misc import limited_field_access_token


def portal_owner_partner(env):
    user = env.user.sudo()
    return user.marstek_owner_id or env["res.partner"].sudo()


def portal_owner_domain(env, field_name):
    owner = portal_owner_partner(env)
    if not owner:
        return [("id", "=", 0)]
    return [(field_name, "=", owner.id)]


def portal_quant_domain(env):
    domain = portal_owner_domain(env, "owner_id")
    domain += [("quantity", ">", 0), ("location_id.usage", "in", ["internal", "transit"]), ("package_id", "!=", False)]
    return domain


def portal_stock_location_options(env, keyword=""):
    if not portal_owner_partner(env):
        return []
    quants = env["stock.quant"].sudo().search(portal_quant_domain(env))
    location_id_set = set()
    for location in quants.mapped("location_id"):
        location_id_set.add(location.id)
        location_id_set.update(int(value) for value in (location.parent_path or "").split("/") if value)
    if not location_id_set:
        return []
    location_domain = [("id", "in", list(location_id_set))]
    if keyword:
        location_domain = expression.AND([
            location_domain,
            ["|", ("name", "ilike", keyword), ("complete_name", "ilike", keyword)],
        ])
    locations = env["stock.location"].sudo().search(location_domain, order="complete_name asc, id asc")
    return [
        {"location_id": location.id, "location_name": location.complete_name or location.display_name or ""}
        for location in locations
    ]


def portal_clean_text(value):
    return value or ""


def portal_float(value):
    return float(value or 0.0)


def portal_format_date(value):
    if not value:
        return ""
    if isinstance(value, str):
        return value[:10]
    if isinstance(value, datetime):
        return fields.Date.to_string(value.date())
    if isinstance(value, date):
        return fields.Date.to_string(value)
    return ""


def portal_format_datetime(value):
    if not value:
        return ""
    if isinstance(value, str):
        return value[:19]
    if isinstance(value, datetime):
        return fields.Datetime.to_string(value)
    if isinstance(value, date):
        return fields.Datetime.to_string(datetime.combine(value, time.min))
    return ""


def portal_product_code(product):
    return  product.barcode or product.default_code or ""


def portal_package_container_from_name(name):
    parts = (name or "").split("-")
    if len(parts) >= 3:
        return parts[-2]
    return ""

#给托盘补齐柜号和 BL
def portal_package_shipping_map(env, package_ids, quants=None):
    package_ids = [package_id for package_id in package_ids if package_id]
    if not package_ids:
        return {}

    info_by_package = {
        package_id: {
            "container_no": "",
            "bl_no": "",
        }
        for package_id in package_ids
    }

    move_line_env = env["stock.move.line"].sudo()
    move_lines = move_line_env.search(
        [
            ("result_package_id", "in", package_ids),
            ("picking_id.picking_type_id.code", "=", "incoming"),
        ],
        order="date desc, id desc",
    )

    for move_line in move_lines:
        package = move_line.result_package_id
        if not package:
            continue

        package_id = package.id
        current_info = info_by_package.get(package_id, {})

        if current_info.get("container_no") and current_info.get("bl_no"):
            continue

        picking = move_line.picking_id
        inbound = picking.inbound_order_id

        container_no = (inbound.cntr_no if inbound else "") or picking.cntrno or ""
        bl_no = (inbound.bl_no if inbound else "") or picking.bill_of_lading or ""

        if not container_no and not bl_no:
            continue

        info_by_package[package_id] = {
            "container_no": current_info.get("container_no") or container_no,
            "bl_no": current_info.get("bl_no") or bl_no,
        }

    return info_by_package



#通过柜号或 BL 反查托盘 ID”
def portal_package_ids_by_shipping(env, field_key, operator, value, owner=None):
    if not value:
        return []

    if field_key not in ("container_no", "bl_no"):
        return []

    operator = operator or "ilike"
    if operator not in ("=", "!=", "ilike", "not ilike", "=ilike"):
        operator = "ilike"

    inbound_field = "cntr_no" if field_key == "container_no" else "bl_no"
    picking_field = "cntrno" if field_key == "container_no" else "bill_of_lading"

    base_domain = [
        ("result_package_id", "!=", False),
        ("picking_id.picking_type_id.code", "=", "incoming"),
    ]

    shipping_domain = expression.OR([
        [(f"picking_id.inbound_order_id.{inbound_field}", operator, value)],
        [(f"picking_id.{picking_field}", operator, value)],
    ])

    domain = expression.AND([base_domain, shipping_domain])

    if owner:
        owner_domain = expression.OR([
            [("picking_id.inbound_order_id.project.owner", "=", owner.id)],
            [("picking_id.owner_id", "=", owner.id)],
            [("picking_id.partner_id", "=", owner.id)],
        ])
        domain = expression.AND([domain, owner_domain])

    move_lines = env["stock.move.line"].sudo().search(
        domain,
        order="date desc, id desc",
    )
    return list(set(move_lines.mapped("result_package_id").ids))



#把 stock.quant 库存记录整理成前端要的库存行
def portal_stock_rows_from_quants(env, quants, forced_container_no=""):
    info_by_package = portal_package_shipping_map(env, quants.mapped("package_id").ids)
    rows_by_key = {}
    for quant in quants:
        package = quant.package_id
        product = quant.product_id
        location = quant.location_id
        info = info_by_package.get(package.id, {})
        key = (package.id, product.id, location.id)
        row = rows_by_key.setdefault(key, {
            "package_name": package.name or "",
            "container_no": forced_container_no or info.get("container_no") or "",
            "bl_no": info.get("bl_no") or "",
            "product_code": portal_product_code(product),
            "product_name": product.display_name or product.name or "",
            "quantity": 0.0,
            "location_name": location.complete_name or location.display_name or "",
            "inbound_date": portal_format_date(quant.in_date),
            "inbound_date_value": quant.in_date,
        })
        row["quantity"] += portal_float(quant.quantity)
        if quant.in_date and (not row["inbound_date_value"] or quant.in_date < row["inbound_date_value"]):
            row["inbound_date_value"] = quant.in_date
            row["inbound_date"] = portal_format_date(quant.in_date)
    rows = list(rows_by_key.values())
    for row in rows:
        row.pop("inbound_date_value", None)
    return rows



def portal_filter_value(filters, *names):
    if not isinstance(filters, dict):
        return ""
    for name in names:
        value = filters.get(name)
        if value not in (None, False, ""):
            return value
    return ""


def portal_apply_date_filters(domain, filters, field_name, start_names, end_names):
    date_from = portal_filter_value(filters, *start_names)
    date_to = portal_filter_value(filters, *end_names)
    if date_from:
        domain.append((field_name, ">=", date_from))
    if date_to:
        domain.append((field_name, "<=", f"{date_to} 23:59:59" if field_name.endswith("date") or "datetime" in field_name else date_to))
    return domain


def portal_detect_attachment_type(name, doc_type=""):
    doc_type = (doc_type or "").lower()
    if doc_type == "cmr":
        return "CMR"
    if doc_type == "sn_details":
        return "SN_DETAIL"
    if doc_type == "origin":
        return "ORIGIN"
    name_upper = (name or "").upper()
    if "CMR" in name_upper:
        return "CMR"
    if "POD" in name_upper:
        return "POD"
    if "SN" in name_upper or "明细" in (name or ""):
        return "SN_DETAIL"
    return "NORMAL"


def portal_attachment_row(attachment, attachment_type=""):
    datas_fname = attachment.datas_fname if "datas_fname" in attachment._fields else ""
    file_name = attachment.name or datas_fname or ""
    access_token = quote(limited_field_access_token(attachment, "raw"), safe="")
    return {
        "file_name": file_name,
        "file_id": attachment.id,
        "file_type": attachment_type or portal_detect_attachment_type(file_name),
        "file_size": attachment.file_size or 0,
        "mimetype": attachment.mimetype or "",
        "download_url": f"/web/content/{attachment.id}?download=true&access_token={access_token}",
    }


def portal_doc_binary_row(doc, file_type=""):
    file_name = doc.filename or ""
    file_size = 0
    if doc.file:
        try:
            file_size = len(base64.b64decode(doc.file))
        except Exception:
            file_size = 0
    access_token = quote(limited_field_access_token(doc, "file"), safe="")
    return {
        "file_name": file_name,
        "file_id": False,
        "file_type": file_type or portal_detect_attachment_type(file_name, doc.doc_type),
        "file_size": file_size,
        "mimetype": "",
        "download_url": f"/web/content/{doc._name}/{doc.id}/file/{quote(file_name, safe='')}?download=true&access_token={access_token}",
    }


def portal_binary_field_row(record, field_name, filename_field, file_type=""):
    file_name = record[filename_field] or ""
    if not record[field_name]:
        return {}
    file_size = 0
    try:
        file_size = len(base64.b64decode(record[field_name]))
    except Exception:
        file_size = 0
    access_token = quote(limited_field_access_token(record, field_name), safe="")
    return {
        "file_name": file_name,
        "file_id": False,
        "file_type": file_type or portal_detect_attachment_type(file_name),
        "file_size": file_size,
        "mimetype": "",
        "download_url": f"/web/content/{record._name}/{record.id}/{field_name}/{quote(file_name, safe='')}?download=true&access_token={access_token}",
    }



def portal_or_domain(base_domain, extra_domain):
    if not extra_domain:
        return base_domain
    return expression.AND([base_domain, extra_domain])
