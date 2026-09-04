# -*- coding: utf-8 -*-

import base64
from datetime import date, datetime, time
from urllib.parse import quote

from odoo import fields
from odoo.tools.misc import limited_field_access_token


def portal_stock_operation_project_ids(env):
    return env.user.sudo().stock_operation_project_line_ids.ids


def portal_project_domain(env, field_name):
    project_ids = portal_stock_operation_project_ids(env)
    if not project_ids:
        return [("id", "=", 0)]
    return [(field_name, "in", project_ids)]


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
    return product.barcode or product.default_code or ""


def portal_product_name(product):
    if not product:
        return ""
    product_code = product.barcode or product.default_code or ""
    product_name = product.name or ""
    return "[%s] %s" % (product_code, product_name) if product_code and product_name else product_code or product_name


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
        "file_name": file_name, "file_id": attachment.id, "file_type": attachment_type or portal_detect_attachment_type(file_name),
        "file_size": attachment.file_size or 0, "mimetype": attachment.mimetype or "",
        "download_url": f"/web/content/{attachment.id}?download=true&access_token={access_token}",
    }


def portal_doc_binary_row(doc, file_type=""):
    file_name = doc.filename or ""
    try:
        file_size = len(base64.b64decode(doc.file)) if doc.file else 0
    except Exception:
        file_size = 0
    access_token = quote(limited_field_access_token(doc, "file"), safe="")
    return {
        "file_name": file_name, "file_id": False, "file_type": file_type or portal_detect_attachment_type(file_name, doc.doc_type),
        "file_size": file_size, "mimetype": "",
        "download_url": f"/web/content/{doc._name}/{doc.id}/file/{quote(file_name, safe='')}?download=true&access_token={access_token}",
    }


def portal_binary_field_row(record, field_name, filename_field, file_type=""):
    file_name = record[filename_field] or ""
    if not record[field_name]:
        return {}
    try:
        file_size = len(base64.b64decode(record[field_name]))
    except Exception:
        file_size = 0
    access_token = quote(limited_field_access_token(record, field_name), safe="")
    return {
        "file_name": file_name, "file_id": False, "file_type": file_type or portal_detect_attachment_type(file_name),
        "file_size": file_size, "mimetype": "",
        "download_url": f"/web/content/{record._name}/{record.id}/{field_name}/{quote(file_name, safe='')}?download=true&access_token={access_token}",
    }
