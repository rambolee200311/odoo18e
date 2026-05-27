# -*- coding: utf-8 -*-

import base64
import os
from io import BytesIO

from odoo import _, fields, models
from odoo.exceptions import UserError

try:
    import openpyxl
except ImportError:
    openpyxl = None

try:
    import xlrd
except ImportError:
    xlrd = None


class OutboundProductImportWizard(models.TransientModel):
    _name = "chenyang.chemical.outbound.product.import.wizard"
    _description = "Chenyang Chemical Outbound Product Import Wizard"
    _order = "id desc"

    outbound_order_id = fields.Many2one("world.depot.outbound.order", string="Outbound Order", required=True, readonly=True, index=True, copy=False)
    reference = fields.Char(string="Reference", required=True, copy=False, readonly=True)
    file = fields.Binary(string="Excel File", required=True, copy=False)
    filename = fields.Char(string="Filename", copy=False)

    def action_import_excel(self):
        for rec in self:
            outbound_order = rec.outbound_order_id
            if outbound_order.state != "new":
                raise UserError(_("Only new in  outbound orders can import products."))
            if outbound_order.outbound_order_product_ids:
                raise UserError(_("This outbound order already has pallet/product lines."))
            if not outbound_order.reference:
                raise UserError(_("Outbound order reference is required before importing products."))
            if not rec.file:
                raise UserError(_("Please upload an Excel file."))

            file_content = base64.b64decode(rec.file)
            extension = os.path.splitext(rec.filename or "")[1].lower()
            if extension not in (".xlsx", ".xls"):
                raise UserError(_("Only .xlsx and .xls files are supported."))

            required_headers = ["reference", "pallet_no", "product", "product_ean", "quantity","is_lot","lot_name","m_date","e_date"]

            def cell_to_text(value):
                if value is None:
                    return ""
                if isinstance(value, float) and value.is_integer():
                    return str(int(value))
                return str(value).strip()

            def cell_to_quantity(value, row_number):
                if value is None or cell_to_text(value) == "":
                    raise UserError(_("Row %s: quantity is required.") % row_number)
                try:
                    quantity = float(value)
                except (TypeError, ValueError):
                    raise UserError(_("Row %s: quantity must be a number.") % row_number)
                if quantity <= 0:
                    raise UserError(_("Row %s: quantity must be greater than 0.") % row_number)
                return quantity

            def append_row(rows, header_map, row_values, row_number):
                if not any(cell_to_text(value) for value in row_values):
                    return
                row_data = {}
                for header in header_map:
                    row_data[header] = row_values[header_map[header]] if header_map[header] < len(row_values) else ""
                rows.append((row_number, row_data))

            def read_xlsx_rows():
                if openpyxl is None:
                    raise UserError(_("openpyxl is required to import .xlsx files."))
                workbook = openpyxl.load_workbook(BytesIO(file_content), read_only=True, data_only=True)
                sheet = workbook.active
                rows_iter = sheet.iter_rows(values_only=True)
                try:
                    header_row = next(rows_iter)
                except StopIteration:
                    raise UserError(_("The Excel file is empty."))
                header_map = {cell_to_text(value).lower(): index for index, value in enumerate(header_row)}
                missing_headers = [header for header in required_headers if header not in header_map]
                if missing_headers:
                    raise UserError(_("Missing required headers: %s") % ", ".join(missing_headers))
                rows = []
                for row_number, row_values in enumerate(rows_iter, start=2):
                    append_row(rows, header_map, row_values, row_number)
                return rows

            def read_xls_rows():
                if xlrd is None:
                    raise UserError(_("xlrd is required to import .xls files."))
                workbook = xlrd.open_workbook(file_contents=file_content)
                if workbook.nsheets < 1:
                    raise UserError(_("The Excel file is empty."))
                sheet = workbook.sheet_by_index(0)
                if sheet.nrows < 1:
                    raise UserError(_("The Excel file is empty."))
                header_row = sheet.row_values(0)
                header_map = {cell_to_text(value).lower(): index for index, value in enumerate(header_row)}
                missing_headers = [header for header in required_headers if header not in header_map]
                if missing_headers:
                    raise UserError(_("Missing required headers: %s") % ", ".join(missing_headers))
                rows = []
                for row_index in range(1, sheet.nrows):
                    append_row(rows, header_map, sheet.row_values(row_index), row_index + 1)
                return rows

            if extension == ".xlsx":
                rows = read_xlsx_rows()
            else:
                rows = read_xls_rows()
            if not rows:
                raise UserError(_("The Excel file has no data rows."))

            product_model = rec.env["product.product"].sudo()
            pallet_data = {}
            for row_number, row_data in rows:
                reference = cell_to_text(row_data.get("reference"))
                pallet_no = cell_to_text(row_data.get("pallet_no"))
                product_name = cell_to_text(row_data.get("product"))
                product_ean = cell_to_text(row_data.get("product_ean"))
                quantity = cell_to_quantity(row_data.get("quantity"), row_number)
                pallet_type = cell_to_text(row_data.get("pallet_type"))
                remark = cell_to_text(row_data.get("remark"))

                if reference != outbound_order.reference:
                    raise UserError(_("Row %s: reference must be %s.") % (row_number, outbound_order.reference))
                if not pallet_no:
                    raise UserError(_("Row %s: pallet_no is required.") % row_number)
                if not product_name:
                    raise UserError(_("Row %s: product is required.") % row_number)
                if not product_ean:
                    raise UserError(_("Row %s: product_ean is required.") % row_number)

                product = product_model.search([("barcode", "=", product_ean)], limit=1)
                if not product:
                    products = product_model.search([("name", "=", product_name)], limit=2)
                    if not products:
                        raise UserError(_("Row %s: product not found by EAN or product name.") % row_number)
                    if len(products) > 1:
                        raise UserError(_("Row %s: product name matches multiple products.") % row_number)
                    product = products

                if pallet_no not in pallet_data:
                    pallet_data[pallet_no] = {
                        "line_source": "import",
                        "pallet_type": pallet_type,
                        "pallet_no": pallet_no,
                        "pallets": 1,
                        "inbound_order_product_pallet_ids": [],
                    }
                elif pallet_type and not pallet_data[pallet_no]["pallet_type"]:
                    pallet_data[pallet_no]["pallet_type"] = pallet_type

                product_vals = {
                    "line_source": "import",
                    "product_id": product.id,
                    "quantity": quantity,
                }
                if remark:
                    product_vals["remark"] = remark
                pallet_data[pallet_no]["inbound_order_product_pallet_ids"].append((0, 0, product_vals))

            inbound_order.write({
                "inbound_order_product_ids": [(0, 0, vals) for vals in pallet_data.values()],
            })

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Import Products"),
                    "message": _("Imported %s pallets and %s product lines.") % (len(pallet_data), len(rows)),
                    "sticky": False,
                    "next": {
                        "type": "ir.actions.act_window",
                        "name": _("Inbound Order"),
                        "res_model": "world.depot.inbound.order",
                        "view_mode": "form",
                        "views": [(False, "form")],
                        "res_id": inbound_order.id,
                        "target": "current",
                    },
                },
            }
        return {"type": "ir.actions.act_window_close"}
