# -*- coding: utf-8 -*-

from odoo.osv import expression
from odoo.addons.stock_operation_portal.models.utils import (
    portal_attachment_row, portal_binary_field_row, portal_detect_attachment_type, portal_doc_binary_row,
    portal_format_date, portal_format_datetime, portal_product_code, portal_project_domain,
    portal_stock_operation_project_ids,
)


def portal_stock_location_ids(env):
    projects = env.user.sudo().stock_operation_project_line_ids
    return projects.mapped("portal_stock_location_line_ids").ids

def portal_project_package_ids(env):
    project_ids = portal_stock_operation_project_ids(env)
    if not project_ids:
        return []
    move_lines = env["stock.move.line"].sudo().search([
        ("state", "=", "done"),
        ("picking_id.picking_type_id.code", "=", "incoming"),
        ("picking_id.inbound_order_id.project", "in", project_ids),
        ("result_package_id", "!=", False),
    ], order="date asc, id asc")
    return move_lines.mapped("result_package_id").ids


def portal_location_is_allowed(env, location_id):
    if not str(location_id).isdigit():
        return False
    root_location_ids = portal_stock_location_ids(env)
    if not root_location_ids:
        return False
    return int(location_id) in root_location_ids


def portal_quant_domain(env):
    domain = [("quantity", ">", 0), ("location_id.usage", "in", ["internal", "transit"]), ("package_id", "!=", False)]
    package_ids = portal_project_package_ids(env)
    if not package_ids:
        return [("id", "=", 0)]
    domain.append(("package_id", "in", package_ids))
    return domain


def portal_stock_location_options(env, keyword=""):
    root_location_ids = portal_stock_location_ids(env)
    if not root_location_ids:
        return []
    location_domain = [("id", "in", root_location_ids)]
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


def portal_or_domain(base_domain, extra_domain):
    if not extra_domain:
        return base_domain
    return expression.AND([base_domain, extra_domain])
