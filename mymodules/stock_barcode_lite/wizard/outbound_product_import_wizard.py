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
    _name = "outbound.product.import.wizard"
    _description = "Outbound Product Import Wizard"
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

            required_headers = ["reference", "pallet_no", "de_palletize","product", "product_ean", "quantity","is_lot"]

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

            def cell_to_date(value, row_number, field_name):
                value_text = cell_to_text(value)
                if not value_text:
                    return False
                try:
                    return fields.Date.to_date(value_text)
                except ValueError:
                    raise UserError(_("Row %s: %s must be a valid date YYYY-MM-DD.") % (row_number, field_name))

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
            pallet_data_list = []
            for row_number, row_data in rows:
                reference = cell_to_text(row_data.get("reference"))
                pallet_no = cell_to_text(row_data.get("pallet_no"))
                de_palletize = cell_to_text(row_data.get("de_palletize"))
                product_name = cell_to_text(row_data.get("product"))
                product_ean = cell_to_text(row_data.get("product_ean"))
                quantity = cell_to_quantity(row_data.get("quantity"), row_number)
                is_lot = cell_to_text(row_data.get("is_lot"))
                lot_name = cell_to_text(row_data.get("lot_name"))
                m_date = cell_to_date(row_data.get("m_date"), row_number, "m_date")
                e_date = cell_to_date(row_data.get("e_date"), row_number, "e_date")
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
                if de_palletize not in ("N", "Y"):
                    raise UserError(_("Row %s: de_palletize must be N or Y.") % row_number)

                if is_lot not in ("N", "Y"):
                    raise UserError(_("Row %s: is_lot must be N or Y.") % row_number)

                if is_lot == "Y" and not lot_name:
                    raise UserError(_("Row %s: lot_name is required when is_lot is Y.") % row_number)
                product = product_model.search([("barcode", "=", product_ean)], limit=1)
                if not product:
                    products = product_model.search([("name", "=", product_name)], limit=2)
                    if not products:
                        raise UserError(_("Row %s: product not found by EAN or product name.") % row_number)
                    if len(products) > 1:
                        raise UserError(_("Row %s: product name matches multiple products.") % row_number)
                    product = products


                product_vals =  {
                    "creation_source": "import",
                    "pallet_type": pallet_type,
                    "pallet_no": pallet_no,
                    "de_palletize": de_palletize,
                    "pallets": 1,
                    "product_id": product.id,
                    "quantity": quantity,
                    "is_lot": is_lot,
                    "lot_name": lot_name,
                    "m_date": m_date,
                    "e_date": e_date,
                    "remark": remark,

                }
                pallet_data_list.append(product_vals)
            outbound_order.write({
                "outbound_order_product_ids": [(0, 0, vals) for vals in pallet_data_list],
            })

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Import Products"),
                    "message": _("Imported %s product lines.") % len(pallet_data_list),
                    "sticky": False,
                    "next": {
                        "type": "ir.actions.act_window",
                        "name": _("Outbound Order"),
                        "res_model": "world.depot.outbound.order",
                        "view_mode": "form",
                        "views": [(False, "form")],
                        "res_id": outbound_order.id,
                        "target": "current",
                    },
                },
            }
        return {"type": "ir.actions.act_window_close"}
